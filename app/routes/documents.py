"""Document routes — list documents and handle uploads."""

import logging
import os
from pathlib import Path

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, url_for
from werkzeug.utils import secure_filename

from app import get_index_manager, get_rag_engine

logger = logging.getLogger(__name__)

documents_bp = Blueprint("documents", __name__)


@documents_bp.get("/documents")
def list_documents():
    cfg = current_app.config["RAG_CONFIG"]
    docs = _get_document_list(cfg.docs_dir)
    return render_template("documents.html", documents=docs)


@documents_bp.post("/upload")
def upload():
    cfg = current_app.config["RAG_CONFIG"]

    if "files" not in request.files:
        flash("Keine Datei ausgewählt", "error")
        return redirect(url_for("documents.list_documents"))

    uploaded = 0
    errors = []

    for file in request.files.getlist("files"):
        if not file.filename:
            continue
        if not cfg.allowed_file(file.filename):
            errors.append(f"{file.filename}: Dateityp nicht erlaubt")
            continue

        filename = secure_filename(file.filename)
        dest = cfg.docs_dir / filename
        file.save(str(dest))
        logger.info("Uploaded: %s", filename)
        uploaded += 1

    if uploaded:
        # Trigger re-index synchronously (blocks this request ~30-90s on Pi)
        logger.info("Triggering re-index after upload …")
        try:
            get_rag_engine().rebuild_index()
            get_index_manager().update_meta()
        except Exception as exc:
            logger.exception("Re-index failed")
            errors.append(f"Re-Indexierung fehlgeschlagen: {exc}")

        flash(f"{uploaded} Datei(en) hochgeladen und indiziert", "success")
    else:
        flash("Keine gültigen Dateien hochgeladen", "error")

    for err in errors:
        flash(err, "error")

    return redirect(url_for("documents.list_documents"))


# ------------------------------------------------------------------
# Helper
# ------------------------------------------------------------------

def _get_document_list(docs_dir: Path) -> list[dict]:
    result = []
    for p in sorted(docs_dir.glob("**/*")):
        if p.is_file() and p.suffix.lower() in {".pdf", ".txt"}:
            stat = p.stat()
            result.append({
                "name": p.name,
                "size": stat.st_size,
                "mtime": stat.st_mtime,
                "path": str(p.relative_to(docs_dir)),
            })
    return result
