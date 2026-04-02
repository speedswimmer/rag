"""Flask application factory."""

import logging
import os
import uuid

from flask import Flask, g, request as flask_request
from flask_wtf.csrf import CSRFProtect

_csrf = CSRFProtect()

from app.config import Config
from app.database import db
from app.indexer import IndexManager
from app.rag_engine import RAGEngine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Module-level singletons — shared across all requests within a worker
_rag_engine: RAGEngine | None = None
_index_manager: IndexManager | None = None


def get_rag_engine() -> RAGEngine:
    return _rag_engine


def get_index_manager() -> IndexManager:
    return _index_manager


def create_app(config: Config | None = None) -> Flask:
    global _rag_engine, _index_manager

    app = Flask(__name__, template_folder="templates", static_folder="static")

    cfg = config or Config()
    app.config["RAG_CONFIG"] = cfg
    app.config["SECRET_KEY"] = cfg.secret_key
    app.config["MAX_CONTENT_LENGTH"] = cfg.max_content_length
    app.config["WTF_CSRF_TIME_LIMIT"] = None  # Token läuft nicht ab (kein Login)

    _csrf.init_app(app)

    # Database
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{cfg.chat_db_path}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)

    with app.app_context():
        from app import models  # noqa: F401 — registers models with SQLAlchemy
        db.create_all()

    if not os.getenv("ANTHROPIC_API_KEY"):
        logger.error("ANTHROPIC_API_KEY is not set — LLM calls will fail")

    # Initialise singletons
    _index_manager = IndexManager(cfg)
    _rag_engine = RAGEngine(cfg)
    _rag_engine.initialize()

    # Smart indexing: rebuild only when files changed
    if _index_manager.check_changes():
        logger.info("Document changes detected — rebuilding index …")
        _rag_engine.rebuild_index()
        _index_manager.update_meta()
    else:
        logger.info("No document changes — skipping index rebuild")

    # Register blueprints
    from app.routes.admin import admin_bp
    from app.routes.chat import chat_bp
    from app.routes.documents import documents_bp
    from app.routes.info import info_bp

    app.register_blueprint(chat_bp)
    app.register_blueprint(documents_bp)
    app.register_blueprint(info_bp)
    app.register_blueprint(admin_bp)

    from app.routes.conversations import conversations_bp
    app.register_blueprint(conversations_bp)

    # Anonymous session cookie
    @app.before_request
    def ensure_session_cookie():
        sid = flask_request.cookies.get("rag_session_id")
        if sid:
            from app.models import Session as ChatSession
            if not db.session.get(ChatSession, sid):
                chat_session = ChatSession(id=sid)
                db.session.add(chat_session)
                db.session.commit()
            g.session_id = sid
        else:
            g.session_id = str(uuid.uuid4())

    @app.after_request
    def set_session_cookie(response):
        sid = getattr(g, "session_id", None)
        if sid and "rag_session_id" not in flask_request.cookies:
            from app.models import Session as ChatSession
            chat_session = ChatSession(id=sid)
            db.session.add(chat_session)
            db.session.commit()
            response.set_cookie(
                "rag_session_id", sid,
                max_age=365 * 24 * 3600,
                httponly=True,
                samesite="Lax",
            )
        return response

    # Jinja2 custom filter
    import datetime

    @app.template_filter("timestamp_to_str")
    def timestamp_to_str(ts: float) -> str:
        return datetime.datetime.fromtimestamp(ts).strftime("%d.%m.%Y %H:%M")

    # Inject app_name into every template context
    from app.settings import get_app_name

    @app.context_processor
    def inject_app_name():
        return {"app_name": get_app_name()}

    return app
