"""Chat history models — sessions, conversations, messages."""

import uuid
from datetime import datetime, timezone

from app.database import db


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Session(db.Model):
    __tablename__ = "sessions"

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)

    conversations = db.relationship(
        "Conversation", back_populates="session", cascade="all, delete-orphan"
    )


class Conversation(db.Model):
    __tablename__ = "conversations"

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    session_id = db.Column(
        db.String(36), db.ForeignKey("sessions.id"), nullable=False, index=True
    )
    title = db.Column(db.String(100), nullable=False, default="Neue Unterhaltung")
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow, nullable=False)

    session = db.relationship("Session", back_populates="conversations")
    messages = db.relationship(
        "Message", back_populates="conversation", cascade="all, delete-orphan",
        order_by="Message.created_at"
    )


class Message(db.Model):
    __tablename__ = "messages"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    conversation_id = db.Column(
        db.String(36), db.ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    role = db.Column(db.String(10), nullable=False)  # 'user' or 'assistant'
    content = db.Column(db.Text, nullable=False)
    sources = db.Column(db.Text, nullable=True)  # JSON string
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)

    conversation = db.relationship("Conversation", back_populates="messages")
