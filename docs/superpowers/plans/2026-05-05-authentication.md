# Authentication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add role-based authentication with Flask-Login — three roles (leser/user/admin), guest chat access, login page, CLI user management.

**Architecture:** User model in SQLAlchemy with password hashing via werkzeug.security. Flask-Login handles session management. Custom `@role_required` decorator enforces role hierarchy. Existing anonymous session logic stays intact for guests.

**Tech Stack:** Flask-Login, werkzeug.security, SQLAlchemy, Click (Flask CLI)

**Spec:** `docs/superpowers/specs/2026-05-05-authentication-design.md`

---

### Task 1: Add flask-login dependency and User model

**Files:**
- Modify: `requirements.txt`
- Modify: `app/models.py`

- [ ] **Step 1: Add flask-login to requirements.txt**

Add after `flask-sqlalchemy>=3.1`:

```
flask-login>=0.6
```

- [ ] **Step 2: Add User model to app/models.py**

Add these imports at the top of `app/models.py`:

```python
from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash
```

Add the `User` class after the existing imports and helpers, before `Session`:

```python
# Role hierarchy: leser (0) < user (1) < admin (2)
ROLE_LEVELS = {"leser": 0, "user": 1, "admin": 2}


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(10), nullable=False, default="leser")
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def has_role(self, min_role: str) -> bool:
        return ROLE_LEVELS.get(self.role, 0) >= ROLE_LEVELS.get(min_role, 0)
```

- [ ] **Step 3: Install dependency locally**

Run: `pip install flask-login>=0.6`

- [ ] **Step 4: Verify model loads**

Run: `python -c "from app.models import User; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add requirements.txt app/models.py
git commit -m "feat: add User model with role-based auth support"
```

---

### Task 2: Initialize Flask-Login in app factory

**Files:**
- Modify: `app/__init__.py`

- [ ] **Step 1: Add Flask-Login imports and setup**

Add import at the top of `app/__init__.py`, after the existing imports:

```python
from flask_login import LoginManager
```

Add after `_csrf = CSRFProtect()`:

```python
_login_manager = LoginManager()
_login_manager.login_view = "auth.login"
_login_manager.login_message = "Bitte anmelden, um auf diesen Bereich zuzugreifen."
_login_manager.login_message_category = "info"
```

- [ ] **Step 2: Initialize login manager in create_app**

Add inside `create_app()`, after `_csrf.init_app(app)`:

```python
_login_manager.init_app(app)
```

- [ ] **Step 3: Add user_loader callback**

Add inside `create_app()`, after the `_login_manager.init_app(app)` line:

```python
@_login_manager.user_loader
def load_user(user_id):
    from app.models import User
    return db.session.get(User, int(user_id))
```

- [ ] **Step 4: Add admin existence check**

Add inside `create_app()`, after the `db.create_all()` block (inside the `with app.app_context():` block):

```python
from app.models import User
if not User.query.filter_by(role="admin").first():
    logger.warning("Kein Admin-Benutzer vorhanden — bitte mit 'flask create-user' anlegen")
```

- [ ] **Step 5: Inject current_user into templates**

Update the existing `context_processor` to also provide `current_user`:

```python
from flask_login import current_user as _current_user

@app.context_processor
def inject_globals():
    return {"app_name": get_app_name(), "current_user": _current_user}
```

This replaces the existing `inject_app_name` context processor.

- [ ] **Step 6: Verify app starts**

Run: `python -c "from app import create_app; app = create_app(); print('OK')"`
Expected: `OK` (plus the admin warning in log output)

- [ ] **Step 7: Commit**

```bash
git add app/__init__.py
git commit -m "feat: initialize Flask-Login in app factory"
```

---

### Task 3: Create role_required decorator

**Files:**
- Create: `app/auth.py`

- [ ] **Step 1: Create app/auth.py with role_required decorator**

```python
"""Authentication helpers — role_required decorator."""

from functools import wraps

from flask import abort
from flask_login import current_user, login_required


def role_required(min_role: str):
    """Decorator that requires login AND a minimum role level.

    Usage:
        @role_required("admin")
        def admin_dashboard(): ...
    """
    def decorator(f):
        @wraps(f)
        @login_required
        def wrapped(*args, **kwargs):
            if not current_user.has_role(min_role):
                abort(403)
            return f(*args, **kwargs)
        return wrapped
    return decorator
```

- [ ] **Step 2: Verify import**

Run: `python -c "from app.auth import role_required; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add app/auth.py
git commit -m "feat: add role_required decorator"
```

---

### Task 4: Create auth routes (login/logout)

**Files:**
- Create: `app/routes/auth.py`

- [ ] **Step 1: Create app/routes/auth.py**

```python
"""Auth routes — login and logout."""

import logging

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app.database import db
from app.models import User

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__)


@auth_bp.get("/login")
def login():
    if current_user.is_authenticated:
        return redirect(url_for("chat.index"))
    return render_template("login.html")


@auth_bp.post("/login")
def login_post():
    if current_user.is_authenticated:
        return redirect(url_for("chat.index"))

    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""

    user = User.query.filter_by(username=username).first()

    if not user or not user.check_password(password) or not user.is_active:
        flash("Benutzername oder Passwort falsch", "error")
        return render_template("login.html"), 401

    login_user(user, remember=True)
    logger.info("User '%s' logged in (role: %s)", user.username, user.role)

    next_page = request.args.get("next")
    if next_page and next_page.startswith("/"):
        return redirect(next_page)
    return redirect(url_for("chat.index"))


@auth_bp.post("/logout")
@login_required
def logout():
    logger.info("User '%s' logged out", current_user.username)
    logout_user()
    return redirect(url_for("chat.index"))
```

- [ ] **Step 2: Register blueprint in app/__init__.py**

Add after the existing blueprint registrations:

```python
from app.routes.auth import auth_bp
app.register_blueprint(auth_bp)
```

- [ ] **Step 3: Set remember cookie duration**

Add in `create_app()`, after the `app.config["WTF_CSRF_TIME_LIMIT"]` line:

```python
from datetime import timedelta
app.config["REMEMBER_COOKIE_DURATION"] = timedelta(days=30)
app.config["REMEMBER_COOKIE_HTTPONLY"] = True
app.config["REMEMBER_COOKIE_SAMESITE"] = "Lax"
```

- [ ] **Step 4: Commit**

```bash
git add app/routes/auth.py app/__init__.py
git commit -m "feat: add login/logout routes"
```

---

### Task 5: Create login template

**Files:**
- Create: `app/templates/login.html`

- [ ] **Step 1: Create app/templates/login.html**

```html
{% extends "base.html" %}
{% block title %}Anmelden — {{ app_name }}{% endblock %}

{% block content %}
<div class="login-container">
  <div class="login-card">
    <div class="login-header">
      <h1 class="login-title">{{ app_name }}</h1>
      <p class="login-subtitle">Anmeldung</p>
    </div>

    {% with messages = get_flashed_messages(with_categories=true) %}
      {% for category, message in messages %}
        <div class="login-error">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
          </svg>
          {{ message }}
        </div>
      {% endfor %}
    {% endwith %}

    <form method="POST" action="{{ url_for('auth.login_post', next=request.args.get('next', '')) }}">
      <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">

      <label class="login-label" for="username">Benutzername</label>
      <input class="login-input" type="text" id="username" name="username"
             required autocomplete="username" autofocus>

      <label class="login-label" for="password">Passwort</label>
      <input class="login-input" type="password" id="password" name="password"
             required autocomplete="current-password">

      <button class="login-button" type="submit">Anmelden</button>
    </form>

    <div class="login-guest">
      Kein Konto? <a href="{{ url_for('chat.index') }}">Als Gast zum Chat &rarr;</a>
    </div>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 2: Commit**

```bash
git add app/templates/login.html
git commit -m "feat: add login template"
```

---

### Task 6: Add login page styles

**Files:**
- Modify: `app/static/style.css`

- [ ] **Step 1: Add login styles to style.css**

Append to the end of `app/static/style.css`:

```css
/* ============================================================
   Login page
   ============================================================ */
.login-container {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: calc(100vh - 54px);
  padding: 2rem;
}

.login-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-xl);
  padding: 2.5rem;
  width: 100%;
  max-width: 400px;
  box-shadow: var(--shadow);
}

.login-header {
  text-align: center;
  margin-bottom: 2rem;
}

.login-title {
  font-size: 1.6rem;
  font-weight: 700;
  color: var(--accent);
  margin-bottom: .25rem;
}

.login-subtitle {
  color: var(--text-muted);
  font-size: .9rem;
}

.login-error {
  display: flex;
  align-items: center;
  gap: .5rem;
  background: var(--error-bg);
  border: 1px solid rgba(248,113,113,.25);
  border-radius: var(--radius);
  padding: .7rem 1rem;
  margin-bottom: 1.25rem;
  color: var(--error);
  font-size: .85rem;
}

.login-label {
  display: block;
  color: var(--text-muted);
  font-size: .75rem;
  text-transform: uppercase;
  letter-spacing: .04em;
  margin-bottom: .4rem;
}

.login-input {
  width: 100%;
  background: var(--bg-input);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: .75rem 1rem;
  color: var(--text);
  font-size: .95rem;
  font-family: inherit;
  margin-bottom: 1.1rem;
  transition: border-color var(--transition);
}

.login-input:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-glow);
}

.login-button {
  width: 100%;
  background: var(--accent);
  border: none;
  border-radius: var(--radius);
  padding: .8rem;
  color: #fff;
  font-size: 1rem;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  transition: background var(--transition);
  margin-top: .5rem;
}

.login-button:hover {
  background: var(--accent-hover);
}

.login-guest {
  text-align: center;
  margin-top: 1.5rem;
  color: var(--text-muted);
  font-size: .85rem;
}

.login-guest a {
  color: var(--accent);
  text-decoration: none;
}

.login-guest a:hover {
  text-decoration: underline;
}
```

- [ ] **Step 2: Commit**

```bash
git add app/static/style.css
git commit -m "feat: add login page styles"
```

---

### Task 7: Protect routes with role decorators

**Files:**
- Modify: `app/routes/documents.py`
- Modify: `app/routes/admin.py`
- Modify: `app/routes/info.py`

- [ ] **Step 1: Protect document routes**

In `app/routes/documents.py`, add import at the top:

```python
from flask_login import login_required
from app.auth import role_required
```

Add `@login_required` to `list_documents`:

```python
@documents_bp.get("/documents")
@login_required
def list_documents():
```

Add `@role_required("user")` to `upload` and `delete_document`:

```python
@documents_bp.post("/upload")
@role_required("user")
def upload():
```

```python
@documents_bp.delete("/documents/<filename>")
@role_required("user")
def delete_document(filename: str):
```

Note: `index_status` stays unprotected — it's used by the navbar polling for all users.

- [ ] **Step 2: Protect admin routes**

In `app/routes/admin.py`, add import at the top:

```python
from app.auth import role_required
```

Add `@role_required("admin")` to all admin routes:

```python
@admin_bp.get("/admin")
@role_required("admin")
def admin():
```

```python
@admin_bp.post("/admin/rebuild")
@role_required("admin")
def rebuild():
```

```python
@admin_bp.post("/admin/backup")
@role_required("admin")
def backup():
```

```python
@admin_bp.post("/admin/settings")
@role_required("admin")
def save_settings():
```

```python
@admin_bp.post("/admin/system-prompt")
@role_required("admin")
def save_system_prompt_route():
```

- [ ] **Step 3: Protect info route**

In `app/routes/info.py`, add import:

```python
from app.auth import role_required
```

Add decorator:

```python
@info_bp.get("/info")
@role_required("admin")
def info():
```

- [ ] **Step 4: Commit**

```bash
git add app/routes/documents.py app/routes/admin.py app/routes/info.py
git commit -m "feat: protect routes with role-based auth decorators"
```

---

### Task 8: Update navbar for role-based links

**Files:**
- Modify: `app/templates/base.html`

- [ ] **Step 1: Update nav-links section**

Replace the `<div class="nav-links">` block (lines 35-40) with:

```html
    <div class="nav-links">
      <a href="/" class="nav-link {% if request.path == '/' %}active{% endif %}">Chat</a>
      {% if current_user.is_authenticated %}
        <a href="/documents" class="nav-link {% if request.path == '/documents' %}active{% endif %}">Dokumente</a>
        {% if current_user.has_role('admin') %}
          <a href="/admin" class="nav-link {% if request.path == '/admin' %}active{% endif %}">Admin</a>
          <a href="/info" class="nav-link {% if request.path == '/info' %}active{% endif %}">Info</a>
        {% endif %}
      {% endif %}
    </div>
```

- [ ] **Step 2: Add user info / login link to navbar**

Add after the `<div class="index-status" ...>` block (after line 44), before the closing `</nav>`:

```html
    <div class="nav-user">
      {% if current_user.is_authenticated %}
        <span class="nav-username">{{ current_user.username }}</span>
        <span class="nav-separator">&middot;</span>
        <form method="POST" action="{{ url_for('auth.logout') }}" style="display:inline">
          <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
          <button type="submit" class="nav-logout">Abmelden</button>
        </form>
      {% else %}
        <a href="{{ url_for('auth.login') }}" class="nav-login-link">Anmelden</a>
      {% endif %}
    </div>
```

- [ ] **Step 3: Add navbar user styles to style.css**

Append to the nav section in `app/static/style.css`:

```css
/* Nav user section */
.nav-user {
  display: flex;
  align-items: center;
  gap: .4rem;
  margin-left: auto;
  padding-left: 1rem;
  font-size: .85rem;
}

.nav-username {
  color: var(--text-muted);
}

.nav-separator {
  color: var(--text-dim);
}

.nav-logout {
  background: none;
  border: none;
  color: var(--accent);
  font-family: inherit;
  font-size: .85rem;
  cursor: pointer;
  padding: 0;
}

.nav-logout:hover {
  text-decoration: underline;
}

.nav-login-link {
  color: var(--accent);
  text-decoration: none;
  font-size: .85rem;
}

.nav-login-link:hover {
  text-decoration: underline;
}
```

- [ ] **Step 4: Commit**

```bash
git add app/templates/base.html app/static/style.css
git commit -m "feat: role-based navbar with login/logout"
```

---

### Task 9: Add 403 error page

**Files:**
- Create: `app/templates/403.html`
- Modify: `app/__init__.py`

- [ ] **Step 1: Create app/templates/403.html**

```html
{% extends "base.html" %}
{% block title %}Zugriff verweigert — {{ app_name }}{% endblock %}

{% block content %}
<div class="login-container">
  <div class="login-card" style="text-align:center">
    <h1 style="font-size:3rem;color:var(--accent);margin-bottom:.5rem">403</h1>
    <p style="color:var(--text-muted);margin-bottom:1.5rem">Du hast keine Berechtigung für diesen Bereich.</p>
    <a href="/" class="login-button" style="display:inline-block;text-decoration:none;text-align:center">Zurück zum Chat</a>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 2: Register error handler in app/__init__.py**

Add inside `create_app()`, before `return app`:

```python
@app.errorhandler(403)
def forbidden(e):
    return render_template("403.html"), 403
```

Add `render_template` to the existing flask import if not already there (it's already imported in the routes, but not in `__init__.py`):

```python
from flask import Flask, g, render_template, request as flask_request
```

- [ ] **Step 3: Commit**

```bash
git add app/templates/403.html app/__init__.py
git commit -m "feat: add 403 error page"
```

---

### Task 10: Add CLI user management commands

**Files:**
- Modify: `app/__init__.py`

- [ ] **Step 1: Add CLI commands to create_app**

Add inside `create_app()`, before `return app`:

```python
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
```

- [ ] **Step 2: Verify CLI commands work**

Run: `flask list-users`
Expected: `Keine Benutzer vorhanden.`

Run: `flask create-user --help`
Expected: Shows help text with username argument and --role option.

- [ ] **Step 3: Commit**

```bash
git add app/__init__.py
git commit -m "feat: add CLI commands for user management"
```

---

### Task 11: End-to-end verification

**Files:** No changes — manual testing only.

- [ ] **Step 1: Create a test admin user**

Run: `flask create-user admin --role admin`
Enter a test password when prompted.

- [ ] **Step 2: Verify guest access**

Open browser, navigate to `/` — chat should work without login.
Navigate to `/documents` — should redirect to `/login?next=/documents`.
Navigate to `/admin` — should redirect to `/login?next=/admin`.

- [ ] **Step 3: Verify login**

On the login page, enter wrong credentials — error message should appear.
Enter correct admin credentials — should redirect to the `next` URL.
Navbar should show: Chat, Dokumente, Admin, Info, `admin · Abmelden`.

- [ ] **Step 4: Verify role restrictions**

Create a leser user: `flask create-user leser1 --role leser`
Login as leser1 — should see Chat + Dokumente in navbar.
Navigate to `/admin` — should see 403 page.
Navigate to `/documents` — should see document list but no upload button (upload POST is blocked).

- [ ] **Step 5: Verify logout**

Click "Abmelden" — should redirect to chat.
Navbar should show only "Chat" + "Anmelden".
Guest chat should still work.

- [ ] **Step 6: Final commit with version tag**

```bash
git tag v0.9
```

---

### Task 12: Deploy to Pi

- [ ] **Step 1: Push to remote**

```bash
git push origin main:master
git push origin v0.9
```

- [ ] **Step 2: Pull on Pi and install dependency**

```bash
cd /home/jarvis/rag
git pull
venv/bin/pip install -r requirements.txt
```

- [ ] **Step 3: Create admin user on Pi**

```bash
cd /home/jarvis/rag
FLASK_APP=wsgi.py venv/bin/flask create-user admin --role admin
```

- [ ] **Step 4: Restart service**

```bash
sudo systemctl restart rag-web
```

- [ ] **Step 5: Verify on Pi**

Check logs: `sudo journalctl -u rag-web --no-pager -n 20`
Test login at `https://192.168.178.198/login`
