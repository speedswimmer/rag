"""Chat routes — GET / renders the UI, POST /ask streams answers via SSE."""

import json
import logging

from flask import Blueprint, Response, jsonify, render_template, request, stream_with_context

from app import get_rag_engine

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

    if not question:
        return jsonify({"error": "Keine Frage angegeben"}), 400

    if len(question) > _MAX_QUESTION_LENGTH:
        return jsonify({"error": f"Frage zu lang (maximal {_MAX_QUESTION_LENGTH} Zeichen)"}), 400

    logger.info("Question received (stream): %s", question[:80])

    def generate():
        for event in get_rag_engine().ask_stream(question):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return Response(stream_with_context(generate()), mimetype="text/event-stream")
