import os

from sqlalchemy import CheckConstraint, Column, ForeignKey, String, Text, create_engine, text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.environ["DATABASE_URL"]

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Video(Base):
    __tablename__ = "videos"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    youtube_url = Column(Text, nullable=False)
    video_id = Column(Text, nullable=False, unique=True)
    transcript = Column(Text)
    summary = Column(Text)
    created_at = Column(TIMESTAMP, server_default=text("now()"))


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (CheckConstraint("role IN ('user', 'assistant')", name="messages_role_check"),)

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    video_id = Column(Text, ForeignKey("videos.video_id"), nullable=False)
    role = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(TIMESTAMP, server_default=text("now()"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
