"""Flask application factory."""

import logging
import os
import uuid

from flask import Flask, g, render_template, request as flask_request
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect

_csrf = CSRFProtect()

_login_manager = LoginManager()
_login_manager.login_view = "auth.login"
_login_manager.login_message = "Bitte anmelden, um auf diesen Bereich zuzugreifen."
_login_manager.login_message_category = "info"

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


def _migrate_feedback_table(app: Flask) -> None:
    """Add question/answer/sources columns to feedback table if missing."""
    from sqlalchemy import inspect, text
    inspector = inspect(db.engine)
    existing = {col["name"] for col in inspector.get_columns("feedback")}
    new_cols = {"question": "TEXT", "answer": "TEXT", "sources": "TEXT"}
    with db.engine.begin() as conn:
        for col, dtype in new_cols.items():
            if col not in existing:
                conn.execute(text(f"ALTER TABLE feedback ADD COLUMN {col} {dtype}"))
                app.logger.info("Migration: feedback.%s column added", col)
        # Backfill existing feedbacks that have a linked message
        if new_cols.keys() - existing:
            conn.execute(text("""
                UPDATE feedback SET
                    answer = (SELECT m.content FROM messages m WHERE m.id = feedback.message_id),
                    sources = (SELECT m.sources FROM messages m WHERE m.id = feedback.message_id),
                    question = (
                        SELECT u.content FROM messages u
                        WHERE u.conversation_id = (
                            SELECT m2.conversation_id FROM messages m2 WHERE m2.id = feedback.message_id
                        )
                        AND u.role = 'user'
                        AND u.created_at < (
                            SELECT m3.created_at FROM messages m3 WHERE m3.id = feedback.message_id
                        )
                        ORDER BY u.created_at DESC LIMIT 1
                    )
                WHERE feedback.message_id IS NOT NULL AND feedback.answer IS NULL
            """))
            app.logger.info("Migration: existing feedbacks backfilled")


def create_app(config: Config | None = None) -> Flask:
    global _rag_engine, _index_manager

    app = Flask(__name__, template_folder="templates", static_folder="static")

    cfg = config or Config()
    app.config["RAG_CONFIG"] = cfg
    app.config["SECRET_KEY"] = cfg.secret_key
    app.config["MAX_CONTENT_LENGTH"] = cfg.max_content_length
    app.config["WTF_CSRF_TIME_LIMIT"] = None  # Token läuft nicht ab (kein Login)
    from datetime import timedelta
    app.config["REMEMBER_COOKIE_DURATION"] = timedelta(days=30)
    app.config["REMEMBER_COOKIE_HTTPONLY"] = True
    app.config["REMEMBER_COOKIE_SAMESITE"] = "Lax"

    _csrf.init_app(app)
    _login_manager.init_app(app)

    @_login_manager.user_loader
    def load_user(user_id):
        from app.models import User
        return db.session.get(User, int(user_id))

    # Database
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{cfg.chat_db_path}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)

    with app.app_context():
        from app import models  # noqa: F401 — registers models with SQLAlchemy
        db.create_all()
        _migrate_feedback_table(app)

        from app.models import User
        if not User.query.filter_by(role="admin").first():
            logger.warning("Kein Admin-Benutzer vorhanden — bitte mit 'flask create-user' anlegen")

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

    from app.routes.auth import auth_bp
    app.register_blueprint(auth_bp)

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

    # Inject app_name and current_user into every template context
    from app.settings import get_app_name
    from flask_login import current_user as _current_user

    @app.context_processor
    def inject_globals():
        return {"app_name": get_app_name(), "current_user": _current_user}

    @app.errorhandler(403)
    def forbidden(e):
        return render_template("403.html"), 403

    import click

    @app.cli.command("create-user")
    @click.argument("username")
    @click.option("--role", type=click.Choice(["leser", "user", "admin"]), required=True)
    def create_user_cmd(username, role):
        """Create a new user with the given role."""
        from app.models import User
        if User.query.filter_by(username=username).first():
            click.echo(f"Fehler: Benutzer '{username}' existiert bereits.")
            raise SystemExit(1)
        password = click.prompt("Passwort", hide_input=True, confirmation_prompt=True)
        user = User(username=username, role=role)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        click.echo(f"Benutzer '{username}' (Rolle: {role}) angelegt.")

    @app.cli.command("change-password")
    @click.argument("username")
    def change_password_cmd(username):
        """Change the password for an existing user."""
        from app.models import User
        user = User.query.filter_by(username=username).first()
        if not user:
            click.echo(f"Fehler: Benutzer '{username}' nicht gefunden.")
            raise SystemExit(1)
        password = click.prompt("Neues Passwort", hide_input=True, confirmation_prompt=True)
        user.set_password(password)
        db.session.commit()
        click.echo(f"Passwort fuer '{username}' geaendert.")

    @app.cli.command("list-users")
    def list_users_cmd():
        """List all users."""
        from app.models import User
        users = User.query.order_by(User.created_at).all()
        if not users:
            click.echo("Keine Benutzer vorhanden.")
            return
        click.echo(f"{'Username':<20} {'Rolle':<10} {'Aktiv':<8} {'Erstellt'}")
        click.echo("-" * 60)
        for u in users:
            created = u.created_at.strftime("%d.%m.%Y %H:%M")
            active = "Ja" if u.is_active else "Nein"
            click.echo(f"{u.username:<20} {u.role:<10} {active:<8} {created}")

    @app.cli.command("disable-user")
    @click.argument("username")
    def disable_user_cmd(username):
        """Disable a user (prevent login)."""
        from app.models import User
        user = User.query.filter_by(username=username).first()
        if not user:
            click.echo(f"Fehler: Benutzer '{username}' nicht gefunden.")
            raise SystemExit(1)
        user.is_active = False
        db.session.commit()
        click.echo(f"Benutzer '{username}' deaktiviert.")

    return app
