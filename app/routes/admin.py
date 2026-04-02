"""Admin routes — document management, index control, system overview."""

import datetime
import logging
import threading

from flask import Blueprint, current_app, jsonify, render_template, request

from app import get_rag_engine
from app.backup import create_snapshot, get_last_backup
from app.config import APP_VERSION
from app.routes.documents import _get_document_list, _run_index_in_background
from app.settings import get_app_name, save_app_name

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
