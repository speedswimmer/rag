"""Chat routes — GET / renders the UI, POST /ask handles questions."""

import logging

from flask import Blueprint, jsonify, render_template, request

from app import get_rag_engine

logger = logging.getLogger(__name__)

chat_bp = Blueprint("chat", __name__)


@chat_bp.get("/")
def index():
    return render_template("chat.html")


@chat_bp.post("/ask")
def ask():
    data = request.get_json(silent=True) or {}
    question = (data.get("question") or "").strip()

    if not question:
        return jsonify({"error": "Keine Frage angegeben"}), 400

    logger.info("Question received: %s", question[:80])
    try:
        result = get_rag_engine().ask(question)
    except Exception as exc:
        logger.exception("Error during RAG query")
        return jsonify({"error": str(exc)}), 500

    return jsonify(result)
