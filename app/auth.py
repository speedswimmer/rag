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
