"""Sign-in and sign-out routes."""

from datetime import datetime
from urllib.parse import urlsplit

from flask import (
    Blueprint,
    current_app,
    redirect,
    render_template,
    request,
    url_for,
)

from src.services import auth as auth_service

auth_bp = Blueprint("auth", __name__)


def safe_next_path(target: str | None) -> str:
    """Return a local redirect target, or the dashboard for unsafe input."""
    if not isinstance(target, str) or not target.startswith("/"):
        return "/"
    if target.startswith("//") or "\\" in target:
        return "/"
    parts = urlsplit(target)
    if parts.scheme or parts.netloc:
        return "/"
    return target


def _session_cookie_name() -> str:
    return auth_service.AUTH_COOKIE


def _set_session_cookie(response, ticket: auth_service.SessionTicket):
    """Attach the private session cookie to a response."""
    response.set_cookie(
        _session_cookie_name(),
        ticket.token,
        max_age=auth_service.SESSION_SECONDS,
        expires=ticket.expires_at,
        httponly=True,
        secure=current_app.config["AUTH_COOKIE_SECURE"],
        samesite=current_app.config["AUTH_COOKIE_SAMESITE"],
        path="/",
    )
    return response


def _render_login(
    next_path: str,
    error: str | None = None,
    username: str = "",
    status: int = 200,
):
    return (
        render_template(
            "login.html",
            next_path=next_path,
            error=error,
            username=username,
            current_year=datetime.now().year,
        ),
        status,
    )


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """Sign the owner in with a username and password."""
    next_path = safe_next_path(request.values.get("next"))
    token = request.cookies.get(_session_cookie_name())

    if request.method == "GET":
        if auth_service.find_session(token) is not None:
            return redirect(next_path)
        return _render_login(next_path)

    username = request.form.get("username", "")
    password = request.form.get("password", "")
    try:
        ticket = auth_service.authenticate(username, password, previous_token=token)
    except Exception:
        current_app.logger.exception("Authentication failed unexpectedly")
        return _render_login(
            next_path,
            error="Sign-in is unavailable. Please try again later.",
            username=username.strip()[:64],
            status=503,
        )

    if ticket is None:
        return _render_login(
            next_path,
            error="Unable to sign in. Check your details or try again later.",
            username=username.strip()[:64],
            status=401,
        )

    response = redirect(next_path)
    return _set_session_cookie(response, ticket)


@auth_bp.post("/logout")
def logout():
    """Revoke the caller's session and return to the sign-in page."""
    auth_service.revoke_session(request.cookies.get(_session_cookie_name()))
    response = redirect(url_for("auth.login"))
    response.delete_cookie(_session_cookie_name(), path="/")
    return response
