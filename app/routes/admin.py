"""Admin routes — document management, index control, system overview."""

import datetime
import logging
import threading

from flask import Blueprint, current_app, jsonify, render_template, request

from app import get_rag_engine
from app.config import APP_VERSION
from app.routes.documents import _get_document_list, _run_index_in_background
from app.settings import get_app_name, save_app_name

logger = logging.getLogger(__name__)

admin_bp = Blueprint("admin", __name__)


@admin_bp.get("/admin")
def admin():
    cfg = current_app.config["RAG_CONFIG"]
    docs = _get_document_list(cfg.docs_dir)
    return render_template(
        "admin.html",
        documents=docs,
        version=APP_VERSION,
        cfg=cfg,
        chunk_count=_get_chunk_count(),
        last_index=_get_last_index_time(cfg),
    )


@admin_bp.post("/admin/rebuild")
def rebuild():
    threading.Thread(target=_run_index_in_background, daemon=True).start()
    return jsonify({"ok": True})


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
    try:
        engine = get_rag_engine()
        if engine._vectorstore is not None:
            return engine._vectorstore._collection.count()
    except Exception:
        pass
    return None


def _get_last_index_time(cfg) -> str | None:
    try:
        path = cfg.index_meta_path
        if path.exists():
            ts = path.stat().st_mtime
            return datetime.datetime.fromtimestamp(ts).strftime("%d.%m.%Y %H:%M")
    except Exception:
        pass
    return None
