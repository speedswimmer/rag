"""Admin routes — document management, index control, system overview."""

import datetime
import logging
import threading

from flask import Blueprint, current_app, jsonify, render_template, request

from sqlalchemy import func

from app import get_rag_engine
from app.backup import create_snapshot, get_last_backup
from app.config import APP_VERSION
from app.database import db
from app.models import Feedback, Message
from app.routes.documents import _get_document_list, _run_index_in_background
from app.settings import get_app_name, get_system_prompt, save_app_name, save_system_prompt

logger = logging.getLogger(__name__)

admin_bp = Blueprint("admin", __name__)


@admin_bp.get("/admin")
def admin():
    cfg = current_app.config["RAG_CONFIG"]
    docs = _get_document_list(cfg.docs_dir, cfg.allowed_extensions)
    feedback_stats = _get_feedback_stats()
    return render_template(
        "admin.html",
        documents=docs,
        version=APP_VERSION,
        cfg=cfg,
        chunk_count=_get_chunk_count(),
        last_index=_get_last_index_time(cfg),
        last_backup=get_last_backup(cfg.backup_dir),
        system_prompt=get_system_prompt(),
        feedback_stats=feedback_stats,
    )


@admin_bp.post("/admin/rebuild")
def rebuild():
    cfg = current_app.config["RAG_CONFIG"]
    try:
        create_snapshot(cfg.docs_dir, cfg.backup_dir, cfg.backup_keep_days, chat_db_path=cfg.chat_db_path)
    except Exception:
        logger.exception("Snapshot before rebuild failed — continuing anyway")
    threading.Thread(target=_run_index_in_background, daemon=True).start()
    return jsonify({"ok": True})


@admin_bp.post("/admin/backup")
def backup():
    cfg = current_app.config["RAG_CONFIG"]
    try:
        path = create_snapshot(cfg.docs_dir, cfg.backup_dir, cfg.backup_keep_days, chat_db_path=cfg.chat_db_path)
        return jsonify({"ok": True, "name": path.name})
    except Exception:
        logger.exception("Manual snapshot failed")
        return jsonify({"error": "Snapshot fehlgeschlagen"}), 500


@admin_bp.post("/admin/settings")
def save_settings():
    name = (request.json or {}).get("app_name", "").strip()
    if not name:
        return jsonify({"error": "Name darf nicht leer sein"}), 400
    if len(name) > 60:
        return jsonify({"error": "Name zu lang (max. 60 Zeichen)"}), 400
    save_app_name(name)
    return jsonify({"ok": True})


@admin_bp.post("/admin/system-prompt")
def save_system_prompt_route():
    prompt = (request.json or {}).get("system_prompt", "").strip()
    if not prompt:
        return jsonify({"error": "System-Prompt darf nicht leer sein"}), 400
    if len(prompt) > 5000:
        return jsonify({"error": "System-Prompt zu lang (max. 5000 Zeichen)"}), 400
    save_system_prompt(prompt)
    return jsonify({"ok": True})


def _get_feedback_stats() -> dict:
    """Gather feedback statistics for the admin dashboard."""
    counts = dict(
        db.session.query(Feedback.rating, func.count())
        .group_by(Feedback.rating)
        .all()
    )
    total_up = counts.get("up", 0)
    total_down = counts.get("down", 0)

    # Load recent negative feedbacks with the question that triggered them
    negatives = (
        db.session.query(Feedback, Message)
        .join(Message, Feedback.message_id == Message.id)
        .filter(Feedback.rating == "down")
        .order_by(Feedback.created_at.desc())
        .limit(20)
        .all()
    )

    negative_details = []
    for fb, assistant_msg in negatives:
        # Find the preceding user message in the same conversation
        user_msg = (
            Message.query
            .filter(
                Message.conversation_id == assistant_msg.conversation_id,
                Message.role == "user",
                Message.created_at < assistant_msg.created_at,
            )
            .order_by(Message.created_at.desc())
            .first()
        )
        negative_details.append({
            "question": user_msg.content[:120] if user_msg else "—",
            "answer": assistant_msg.content[:200],
            "date": fb.created_at.strftime("%d.%m.%Y %H:%M"),
        })

    return {
        "total_up": total_up,
        "total_down": total_down,
        "total": total_up + total_down,
        "negatives": negative_details,
    }


def _get_chunk_count() -> int | None:
    return get_rag_engine().chunk_count()


def _get_last_index_time(cfg) -> str | None:
    try:
        path = cfg.index_meta_path
        if path.exists():
            ts = path.stat().st_mtime
            return datetime.datetime.fromtimestamp(ts).strftime("%d.%m.%Y %H:%M")
    except Exception:
        pass
    return None
