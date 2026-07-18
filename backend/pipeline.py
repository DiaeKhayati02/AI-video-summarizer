import os

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pydantic import BaseModel, Field

from prompts import QA_PROMPT, STRUCTURED_SUMMARY_PROMPT, SUMMARY_MAP_PROMPT

MODEL_NAME = os.environ.get("MODEL_NAME", "gemini-flash-latest")

# Rough chars-per-token approximation (~4). Gemini Flash's context window is
# far larger than this, but almost no transcript needs more than this budget,
# so we only pay for map_reduce's extra calls when a video genuinely exceeds it.
STUFF_CHAR_LIMIT = 400_000
CHUNK_SIZE = 10_000
CHUNK_OVERLAP = 500


class VideoSummary(BaseModel):
    description: str = Field(description="A concise 2-3 sentence description of the video")
    key_takeaways: list[str] = Field(description="4-6 concise, specific key takeaways")
    suggested_questions: list[str] = Field(description="3 example questions a viewer might ask about this video")


def get_llm(temperature: float = 0.2) -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(model=MODEL_NAME, temperature=temperature)


def summarise_transcript(transcript: str) -> VideoSummary:
    llm = get_llm()
    structured_llm = llm.with_structured_output(VideoSummary)

    if len(transcript) <= STUFF_CHAR_LIMIT:
        chain = STRUCTURED_SUMMARY_PROMPT | structured_llm
        return chain.invoke({"text": transcript})

    splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
    chunks = splitter.split_text(transcript)

    map_chain = SUMMARY_MAP_PROMPT | llm
    section_summaries = [map_chain.invoke({"text": chunk}).text.strip() for chunk in chunks]

    combine_chain = STRUCTURED_SUMMARY_PROMPT | structured_llm
    return combine_chain.invoke({"text": "\n\n".join(section_summaries)})


def answer_question(transcript: str, chat_history: str, question: str) -> str:
    llm = get_llm()
    chain = QA_PROMPT | llm
    result = chain.invoke({"transcript": transcript, "chat_history": chat_history, "question": question})
    return result.text.strip()
