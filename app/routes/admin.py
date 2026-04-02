"""Admin routes — document management, index control, system overview."""

import datetime
import logging
import threading

from flask import Blueprint, current_app, jsonify, render_template, request

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
    return render_template(
        "admin.html",
        documents=docs,
        version=APP_VERSION,
        cfg=cfg,
        chunk_count=_get_chunk_count(),
        last_index=_get_last_index_time(cfg),
        last_backup=get_last_backup(cfg.backup_dir),
        system_prompt=get_system_prompt(),
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


@admin_bp.get("/admin/feedback")
def feedback_data():
    query = (
        db.session.query(Feedback, Message)
        .join(Message, Feedback.message_id == Message.id)
        .order_by(Feedback.created_at.desc())
    )

    filter_param = request.args.get("filter")
    if filter_param == "down":
        query = query.filter(Feedback.rating == "down")

    results = query.all()

    total = Feedback.query.count()
    up_count = Feedback.query.filter_by(rating="up").count()
    down_count = Feedback.query.filter_by(rating="down").count()

    items = []
    for fb, msg in results:
        user_msg = (
            Message.query
            .filter(
                Message.conversation_id == msg.conversation_id,
                Message.role == "user",
                Message.created_at < msg.created_at,
            )
            .order_by(Message.created_at.desc())
            .first()
        )
        question = user_msg.content if user_msg else "—"
        items.append({
            "date": fb.created_at.strftime("%d.%m.%Y %H:%M"),
            "question": (question[:60] + "…") if len(question) > 60 else question,
            "answer_preview": (msg.content[:80] + "…") if len(msg.content) > 80 else msg.content,
            "rating": fb.rating,
            "comment": fb.comment,
        })

    return jsonify({
        "stats": {"total": total, "up": up_count, "down": down_count},
        "items": items,
    })


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
