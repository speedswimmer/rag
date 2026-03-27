"""Document routes — list documents and handle uploads."""

import json
import logging
from pathlib import Path

from flask import Blueprint, Response, current_app, jsonify, render_template, request, stream_with_context
from werkzeug.utils import secure_filename

from app import get_index_manager, get_rag_engine
from app.rag_engine import is_scanned_pdf

# Magic-byte signatures for allowed file types
_MAGIC_BYTES: dict[str, bytes] = {
    "pdf":  b"%PDF-",
    "docx": b"PK\x03\x04",   # DOCX is a ZIP archive
}
# Maximum bytes to read for binary detection in text files
_TXT_SAMPLE_SIZE = 512

logger = logging.getLogger(__name__)

documents_bp = Blueprint("documents", __name__)


@documents_bp.get("/documents")
def list_documents():
    cfg = current_app.config["RAG_CONFIG"]
    docs = _get_document_list(cfg.docs_dir)
    return render_template("documents.html", documents=docs)


@documents_bp.delete("/documents/<filename>")
def delete_document(filename: str):
    cfg = current_app.config["RAG_CONFIG"]

    safe_name = secure_filename(filename)
    if not safe_name or not cfg.allowed_file(safe_name):
        return jsonify({"error": "Ungültiger Dateiname"}), 400

    target = cfg.docs_dir / safe_name
    # Guard against path traversal
    try:
        target.resolve().relative_to(cfg.docs_dir.resolve())
    except ValueError:
        return jsonify({"error": "Ungültiger Pfad"}), 400

    if not target.is_file():
        return jsonify({"error": "Datei nicht gefunden"}), 404

    target.unlink()
    logger.info("Deleted: %s", safe_name)

    try:
        get_rag_engine().rebuild_index()
        get_index_manager().update_meta()
    except Exception as exc:
        logger.exception("Re-index failed after deletion")
        return jsonify({"error": f"Re-Indexierung fehlgeschlagen: {exc}"}), 500

    return jsonify({"ok": True})


@documents_bp.post("/upload")
def upload():
    cfg = current_app.config["RAG_CONFIG"]

    # Read file list before entering the generator (request context required)
    incoming = [
        (f.filename, f)
        for f in request.files.getlist("files")
        if f.filename
    ]

    def generate():
        yield _sse("info", "Dateien werden geprüft …")

        saved: list[str] = []
        errors: list[str] = []

        for original_name, file in incoming:
            if not cfg.allowed_file(original_name):
                errors.append(f"{original_name}: Dateityp nicht erlaubt")
                continue

            ext = original_name.rsplit(".", 1)[1].lower()
            if not _validate_file_content(file, ext):
                errors.append(f"{original_name}: Dateiinhalt entspricht nicht dem erwarteten Format")
                continue

            filename = secure_filename(original_name)
            dest = cfg.docs_dir / filename
            file.save(str(dest))
            logger.info("Uploaded: %s", filename)
            saved.append(filename)

        if not saved:
            msg = errors[0] if errors else "Keine gültigen Dateien hochgeladen"
            yield _sse("error", msg)
            return

        # Detect scanned PDFs for appropriate status message
        scanned = [f for f in saved if f.lower().endswith(".pdf") and is_scanned_pdf(cfg.docs_dir / f)]

        if scanned:
            names = ", ".join(scanned)
            yield _sse(
                "ocr",
                f"Texterkennung (OCR) läuft für: {names} — das kann einige Minuten dauern …",
            )
        else:
            yield _sse("indexing", "Dokumente werden indiziert …")

        try:
            get_rag_engine().rebuild_index()
            get_index_manager().update_meta()
        except Exception as exc:
            logger.exception("Re-index failed after upload")
            yield _sse("error", f"Indexierung fehlgeschlagen: {exc}")
            return

        for err in errors:
            yield _sse("warning", err)

        yield _sse("done", f"{len(saved)} Datei(en) hochgeladen und indiziert")

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


def _validate_file_content(file, ext: str) -> bool:
    """Validate file content via magic bytes (binary types) or null-byte check (text).

    Always seeks back to position 0 so the caller can still save the file.
    """
    if ext == "pdf":
        header = file.read(5)
        file.seek(0)
        return header == _MAGIC_BYTES["pdf"]
    if ext == "docx":
        header = file.read(4)
        file.seek(0)
        return header == _MAGIC_BYTES["docx"]
    if ext == "txt":
        sample = file.read(_TXT_SAMPLE_SIZE)
        file.seek(0)
        # Reject binary content masquerading as plain text
        return b"\x00" not in sample
    return False


def _get_document_list(docs_dir: Path) -> list[dict]:
    result = []
    for p in sorted(docs_dir.glob("**/*")):
        if p.is_file() and p.suffix.lower() in {".pdf", ".txt", ".docx"}:
            stat = p.stat()
            result.append({
                "name": p.name,
                "size": stat.st_size,
                "mtime": stat.st_mtime,
                "path": str(p.relative_to(docs_dir)),
            })
    return result
