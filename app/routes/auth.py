"""Auth routes — login and logout."""

import logging

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

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
    if next_page and next_page.startswith("/") and not next_page.startswith("//"):
        return redirect(next_page)
    return redirect(url_for("chat.index"))


@auth_bp.post("/logout")
@login_required
def logout():
    logger.info("User '%s' logged out", current_user.username)
    logout_user()
    return redirect(url_for("chat.index"))
