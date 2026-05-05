"""Chat history models — sessions, conversations, messages."""

import uuid
from datetime import datetime, timezone

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app.database import db


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# Role hierarchy: leser (0) < user (1) < admin (2)
ROLE_LEVELS = {"leser": 0, "user": 1, "admin": 2}


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(10), nullable=False, default="leser")
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def has_role(self, min_role: str) -> bool:
        return ROLE_LEVELS.get(self.role, 0) >= ROLE_LEVELS.get(min_role, 0)


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
    feedback = db.relationship(
        "Feedback", back_populates="message", uselist=False, cascade="all, delete-orphan"
    )


class Feedback(db.Model):
    __tablename__ = "feedback"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    message_id = db.Column(
        db.Integer, db.ForeignKey("messages.id", ondelete="SET NULL"),
        nullable=True, unique=True, index=True
    )
    rating = db.Column(db.String(4), nullable=False)  # 'up' or 'down'
    comment = db.Column(db.Text, nullable=True)
    question = db.Column(db.Text, nullable=True)
    answer = db.Column(db.Text, nullable=True)
    sources = db.Column(db.Text, nullable=True)  # JSON string
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)

    message = db.relationship("Message", back_populates="feedback")
