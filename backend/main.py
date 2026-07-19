import json
import os

from dotenv import load_dotenv

load_dotenv()

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import Base, Message, Video, engine, get_db
from memory import build_chat_history, save_message
from pipeline import answer_question, summarise_transcript
from transcript import (
    TranscriptFetchBlockedError,
    TranscriptUnavailableError,
    extract_video_id,
    fetch_oembed_metadata,
    fetch_transcript,
)

Base.metadata.create_all(bind=engine)

app = FastAPI(title="YT Summariser")

frontend_origins = os.environ.get("FRONTEND_ORIGIN", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=frontend_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SummariseRequest(BaseModel):
    url: str


class SummariseResponse(BaseModel):
    video_id: str
    title: str | None
    channel_name: str | None
    duration_seconds: int
    description: str
    key_takeaways: list[str]
    suggested_questions: list[str]
    cached: bool


class ChatRequest(BaseModel):
    video_id: str
    question: str


class ChatResponse(BaseModel):
    answer: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/summarise", response_model=SummariseResponse)
def summarise(payload: SummariseRequest, db: Session = Depends(get_db)):
    try:
        video_id = extract_video_id(payload.url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    video = db.query(Video).filter(Video.video_id == video_id).first()
    if video and video.summary:
        try:
            cached_data = json.loads(video.summary)
            return SummariseResponse(video_id=video_id, cached=True, **cached_data)
        except (json.JSONDecodeError, TypeError):
            pass  # summary predates the structured-output format; re-summarise below

    try:
        transcript, duration_seconds = fetch_transcript(video_id)
    except TranscriptUnavailableError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except TranscriptFetchBlockedError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    metadata = fetch_oembed_metadata(payload.url)
    result = summarise_transcript(transcript)

    summary_data = {
        "title": metadata["title"],
        "channel_name": metadata["channel_name"],
        "duration_seconds": duration_seconds,
        "description": result.description,
        "key_takeaways": result.key_takeaways,
        "suggested_questions": result.suggested_questions,
    }

    if video:
        video.transcript = transcript
        video.summary = json.dumps(summary_data)
    else:
        video = Video(
            youtube_url=payload.url,
            video_id=video_id,
            transcript=transcript,
            summary=json.dumps(summary_data),
        )
        db.add(video)
    db.commit()

    return SummariseResponse(video_id=video_id, cached=False, **summary_data)


@app.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest, db: Session = Depends(get_db)):
    video = db.query(Video).filter(Video.video_id == payload.video_id).first()
    if not video or not video.transcript:
        raise HTTPException(status_code=404, detail="Video not found. Summarise it first.")

    chat_history = build_chat_history(db, payload.video_id)
    answer = answer_question(video.transcript, chat_history, payload.question)

    save_message(db, payload.video_id, "user", payload.question)
    save_message(db, payload.video_id, "assistant", answer)

    return ChatResponse(answer=answer)


@app.get("/history/{video_id}")
def history(video_id: str, db: Session = Depends(get_db)):
    messages = (
        db.query(Message)
        .filter(Message.video_id == video_id)
        .order_by(Message.created_at.asc())
        .all()
    )
    return [
        {"role": m.role, "content": m.content, "created_at": m.created_at}
        for m in messages
    ]
