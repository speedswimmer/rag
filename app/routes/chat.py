"""Chat routes — GET / renders the UI, POST /ask streams answers via SSE."""

import json
import logging

from flask import Blueprint, Response, g, jsonify, render_template, request, stream_with_context

from app import get_rag_engine
from app.database import db
from app.models import Conversation, Message

logger = logging.getLogger(__name__)

chat_bp = Blueprint("chat", __name__)

_MAX_QUESTION_LENGTH = 2000


@chat_bp.get("/")
def index():
    return render_template("chat.html")


@chat_bp.post("/ask")
def ask():
    data = request.get_json(silent=True) or {}
    question = (data.get("question") or "").strip()
    conversation_id = data.get("conversation_id")

    if not question:
        return jsonify({"error": "Keine Frage angegeben"}), 400

    if len(question) > _MAX_QUESTION_LENGTH:
        return jsonify({"error": f"Frage zu lang (maximal {_MAX_QUESTION_LENGTH} Zeichen)"}), 400

    if not conversation_id:
        return jsonify({"error": "Keine Konversation angegeben"}), 400

    # Verify conversation belongs to this session
    conv = db.session.get(Conversation, conversation_id)
    if not conv or conv.session_id != g.session_id:
        return jsonify({"error": "Konversation nicht gefunden"}), 404

    logger.info("Question received (stream): %s", question[:80])

    # Save user message
    user_msg = Message(conversation_id=conversation_id, role="user", content=question)
    db.session.add(user_msg)
    db.session.commit()

    # Load conversation history for context
    cfg = request.app.config.get("RAG_CONFIG")
    context_limit = cfg.context_messages if cfg else 5
    history = _load_history(conversation_id, context_limit)

    def generate():
        full_answer = ""
        sources_data = None

        for event in get_rag_engine().ask_stream(question, history=history):
            if event["type"] == "token":
                full_answer += event["data"]
            elif event["type"] == "sources":
                sources_data = event["data"]
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

        # Save assistant message after streaming completes
        if full_answer:
            assistant_msg = Message(
                conversation_id=conversation_id,
                role="assistant",
                content=full_answer,
                sources=json.dumps(sources_data, ensure_ascii=False) if sources_data else None,
            )
            db.session.add(assistant_msg)

            # Update conversation title from first question if still default
            if conv.title == "Neue Unterhaltung":
                conv.title = question[:50]

            # Touch updated_at so sidebar sorts correctly
            from datetime import datetime, timezone
            conv.updated_at = datetime.now(timezone.utc)

            db.session.commit()

    return Response(stream_with_context(generate()), mimetype="text/event-stream")


def _load_history(conversation_id: str, limit: int) -> list[dict]:
    """Load the last N exchanges (user+assistant pairs) from the conversation."""
    msgs = (
        Message.query
        .filter_by(conversation_id=conversation_id)
        .order_by(Message.created_at)
        .all()
    )
    # Exclude the just-saved user message (last one) — it's the current question
    if msgs and msgs[-1].role == "user":
        msgs = msgs[:-1]

    # Take last N*2 messages (N exchanges = N user + N assistant)
    recent = msgs[-(limit * 2):] if msgs else []
    return [{"role": m.role, "content": m.content} for m in recent]
