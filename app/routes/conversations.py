"""Conversation CRUD routes."""

import json
import logging

from flask import Blueprint, g, jsonify, request

from app.database import db
from app.models import Conversation, Message

logger = logging.getLogger(__name__)

conversations_bp = Blueprint("conversations", __name__)


@conversations_bp.get("/conversations")
def list_conversations():
    """Return all conversations for the current session, newest first."""
    convs = (
        Conversation.query
        .filter_by(session_id=g.session_id)
        .order_by(Conversation.updated_at.desc())
        .all()
    )
    return jsonify([
        {
            "id": c.id,
            "title": c.title,
            "created_at": c.created_at.isoformat(),
            "updated_at": c.updated_at.isoformat(),
        }
        for c in convs
    ])


@conversations_bp.post("/conversations")
def create_conversation():
    """Create a new conversation and return its ID."""
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "Neue Unterhaltung")[:100]

    conv = Conversation(session_id=g.session_id, title=title)
    db.session.add(conv)
    db.session.commit()

    return jsonify({"id": conv.id, "title": conv.title}), 201


@conversations_bp.delete("/conversations/<conversation_id>")
def delete_conversation(conversation_id):
    """Delete a conversation and all its messages."""
    conv = db.session.get(Conversation, conversation_id)
    if not conv or conv.session_id != g.session_id:
        return jsonify({"error": "Nicht gefunden"}), 404

    db.session.delete(conv)
    db.session.commit()
    return "", 204


@conversations_bp.get("/conversations/<conversation_id>/messages")
def get_messages(conversation_id):
    """Return all messages in a conversation."""
    conv = db.session.get(Conversation, conversation_id)
    if not conv or conv.session_id != g.session_id:
        return jsonify({"error": "Nicht gefunden"}), 404

    msgs = (
        Message.query
        .filter_by(conversation_id=conversation_id)
        .order_by(Message.created_at)
        .all()
    )
    return jsonify([
        {
            "id": m.id,
            "role": m.role,
            "content": m.content,
            "sources": json.loads(m.sources) if m.sources else None,
            "created_at": m.created_at.isoformat(),
            "feedback": {"rating": m.feedback.rating, "comment": m.feedback.comment}
            if m.feedback else None,
        }
        for m in msgs
    ])
