"""Chat routes — GET / renders the UI, POST /ask handles questions."""

import logging

from flask import Blueprint, jsonify, render_template, request

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

    logger.info("Question received: %s", question[:80])
    try:
        result = get_rag_engine().ask(question)
    except Exception:
        logger.exception("Error during RAG query")
        return jsonify({"error": "Es ist ein interner Fehler aufgetreten. Bitte erneut versuchen."}), 500

    return jsonify(result)
