from sqlalchemy.orm import Session

from database import Message

# A "turn" is one user + assistant pair. Capping here keeps both the DB read
# and the prompt bounded, instead of replaying a video's entire chat history.
MAX_TURNS = 8


def load_recent_messages(db: Session, video_id: str, max_turns: int = MAX_TURNS) -> list[Message]:
    rows = (
        db.query(Message)
        .filter(Message.video_id == video_id)
        .order_by(Message.created_at.desc())
        .limit(max_turns * 2)
        .all()
    )
    return list(reversed(rows))


def build_chat_history(db: Session, video_id: str, max_turns: int = MAX_TURNS) -> str:
    messages = load_recent_messages(db, video_id, max_turns)
    lines = [f"{'User' if m.role == 'user' else 'Assistant'}: {m.content}" for m in messages]
    return "\n".join(lines)


def save_message(db: Session, video_id: str, role: str, content: str) -> Message:
    message = Message(video_id=video_id, role=role, content=content)
    db.add(message)
    db.commit()
    db.refresh(message)
    return message
