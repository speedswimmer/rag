"""Info route — system version and configuration overview."""

from flask import Blueprint, current_app, render_template

from app.auth import role_required
from app.config import APP_VERSION

info_bp = Blueprint("info", __name__)


@info_bp.get("/info")
@role_required("admin")
def info():
    cfg = current_app.config["RAG_CONFIG"]
    return render_template("info.html", version=APP_VERSION, cfg=cfg)
