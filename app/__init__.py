"""Flask application factory."""

import logging
import os

from flask import Flask
from flask_wtf.csrf import CSRFProtect

_csrf = CSRFProtect()

from app.config import Config
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
    from app.routes.chat import chat_bp
    from app.routes.documents import documents_bp
    from app.routes.info import info_bp

    app.register_blueprint(chat_bp)
    app.register_blueprint(documents_bp)
    app.register_blueprint(info_bp)

    # Jinja2 custom filter
    import datetime

    @app.template_filter("timestamp_to_str")
    def timestamp_to_str(ts: float) -> str:
        return datetime.datetime.fromtimestamp(ts).strftime("%d.%m.%Y %H:%M")

    return app
