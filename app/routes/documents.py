"""Document routes — list documents and handle uploads."""

import hashlib
import json
import logging
import threading
from pathlib import Path
from urllib.parse import unquote

from flask import Blueprint, Response, current_app, jsonify, render_template, request, stream_with_context
from werkzeug.utils import secure_filename

from app import get_index_manager, get_rag_engine
from app.rag_engine import is_scanned_pdf

# Magic-byte signatures for allowed file types
_MAGIC_BYTES: dict[str, bytes] = {
    "pdf":  b"%PDF-",
    "docx": b"PK\x03\x04",   # DOCX is a ZIP archive
}
_TXT_SAMPLE_SIZE = 512

logger = logging.getLogger(__name__)

documents_bp = Blueprint("documents", __name__)

# ------------------------------------------------------------------
# Background indexing state (shared across threads, single worker)
# ------------------------------------------------------------------

_status_lock = threading.Lock()
_index_status: dict = {"state": "idle", "message": ""}
_index_build_lock = threading.Lock()  # prevents concurrent rebuilds


def _set_status(state: str, message: str) -> None:
    with _status_lock:
        _index_status["state"] = state
        _index_status["message"] = message


def _get_status() -> dict:
    with _status_lock:
        return dict(_index_status)


def _run_index_in_background() -> None:
    """Rebuild index in a daemon thread. Called after files are saved."""
    if not _index_build_lock.acquire(blocking=False):
        logger.info("Index rebuild already running — skipping concurrent request")
        return
    try:
        _set_status("running", "Index wird aufgebaut …")
        get_rag_engine().rebuild_index()
        get_index_manager().update_meta()
        _set_status("done", "Index aktualisiert")
        logger.info("Background index rebuild complete")
    except Exception:
        logger.exception("Background index rebuild failed")
        _set_status("error", "Indexierung fehlgeschlagen")
    finally:
        _index_build_lock.release()


# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------

@documents_bp.get("/documents")
def list_documents():
    cfg = current_app.config["RAG_CONFIG"]
    docs = _get_document_list(cfg.docs_dir, cfg.allowed_extensions)
    return render_template("documents.html", documents=docs)


@documents_bp.get("/index/status")
def index_status():
    return jsonify(_get_status())


@documents_bp.delete("/documents/<filename>")
def delete_document(filename: str):
    cfg = current_app.config["RAG_CONFIG"]

    safe_name = secure_filename(unquote(filename))
    if not safe_name or not cfg.allowed_file(safe_name):
        return jsonify({"error": "Ungültiger Dateiname"}), 400

    target = cfg.docs_dir / safe_name
    try:
        target.resolve().relative_to(cfg.docs_dir.resolve())
    except ValueError:
        return jsonify({"error": "Ungültiger Pfad"}), 400

    if not target.is_file():
        return jsonify({"error": "Datei nicht gefunden"}), 404

    target.unlink()
    logger.info("Deleted: %s", safe_name)

    threading.Thread(target=_run_index_in_background, daemon=True).start()

    return jsonify({"ok": True})


@documents_bp.post("/upload")
def upload():
    cfg = current_app.config["RAG_CONFIG"]

    # Save files synchronously while the request context is still active
    saved: list[str] = []
    errors: list[str] = []

    for file in request.files.getlist("files"):
        if not file.filename:
            continue
        if not cfg.allowed_file(file.filename):
            errors.append(f"{file.filename}: Dateityp nicht erlaubt")
            continue

        ext = file.filename.rsplit(".", 1)[1].lower()
        if not _validate_file_content(file, ext):
            errors.append(f"{file.filename}: Dateiinhalt entspricht nicht dem erwarteten Format")
            continue

        # Empty file check
        file.seek(0, 2)  # seek to end
        size = file.tell()
        file.seek(0)
        if size == 0:
            errors.append(f"{file.filename}: Datei ist leer")
            continue

        # Duplicate detection via SHA-256
        file_hash = _compute_hash(file)
        duplicate_name = _find_duplicate(cfg.docs_dir, file_hash, cfg.allowed_extensions)
        if duplicate_name:
            errors.append(f"{file.filename}: Identisch mit bereits vorhandener Datei \"{duplicate_name}\"")
            continue

        filename = secure_filename(file.filename)
        dest = cfg.docs_dir / filename
        file.save(str(dest))
        logger.info("Uploaded: %s", filename)
        saved.append(filename)

    # Detect scanned PDFs before entering generator
    scanned = [f for f in saved if f.lower().endswith(".pdf") and is_scanned_pdf(cfg.docs_dir / f)]

    def generate():
        if not saved:
            msg = errors[0] if errors else "Keine gültigen Dateien hochgeladen"
            yield _sse("error", msg)
            return

        for err in errors:
            yield _sse("warning", err)

        if scanned:
            yield _sse("done", f"{len(saved)} Datei(en) gespeichert — OCR + Indexierung läuft im Hintergrund …")
        else:
            yield _sse("done", f"{len(saved)} Datei(en) gespeichert — Indexierung läuft im Hintergrund …")

        threading.Thread(target=_run_index_in_background, daemon=True).start()

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ------------------------------------------------------------------
# Helper
# ------------------------------------------------------------------

def _sse(event: str, message: str) -> str:
    return f"data: {json.dumps({'event': event, 'message': message})}\n\n"


def _compute_hash(file) -> str:
    """Compute SHA-256 hash of an uploaded file."""
    h = hashlib.sha256()
    while chunk := file.read(8192):
        h.update(chunk)
    file.seek(0)
    return h.hexdigest()


def _find_duplicate(docs_dir: Path, file_hash: str, allowed_extensions: frozenset) -> str | None:
    """Check if a file with the same hash already exists in docs_dir."""
    exts = {"." + ext for ext in allowed_extensions}
    for p in docs_dir.glob("**/*"):
        if not p.is_file() or p.suffix.lower() not in exts:
            continue
        h = hashlib.sha256()
        with open(p, "rb") as f:
            while chunk := f.read(8192):
                h.update(chunk)
        if h.hexdigest() == file_hash:
            return p.name
    return None


def _validate_file_content(file, ext: str) -> bool:
    if ext == "pdf":
        header = file.read(5)
        file.seek(0)
        return header == _MAGIC_BYTES["pdf"]
    if ext == "docx":
        header = file.read(4)
        file.seek(0)
        return header == _MAGIC_BYTES["docx"]
    if ext in ("txt", "md"):
        sample = file.read(_TXT_SAMPLE_SIZE)
        file.seek(0)
        return b"\x00" not in sample
    return False


def _get_document_list(docs_dir: Path, allowed_extensions: frozenset | None = None) -> list[dict]:
    result = []
    exts = {"." + ext for ext in allowed_extensions} if allowed_extensions else {".pdf", ".txt", ".docx", ".md"}
    for p in sorted(docs_dir.glob("**/*")):
        if p.is_file() and p.suffix.lower() in exts:
            stat = p.stat()
            result.append({
                "name": p.name,
                "size": stat.st_size,
                "mtime": stat.st_mtime,
                "path": str(p.relative_to(docs_dir)),
            })
    return result
