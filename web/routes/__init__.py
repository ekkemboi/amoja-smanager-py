"""Web page routes for the dashboard shell."""

from datetime import date, timedelta

from flask import (
    Blueprint,
    current_app,
    g,
    make_response,
    redirect,
    render_template,
    request,
    url_for,
)

from src.services import auth as auth_service

web_bp = Blueprint("web", __name__)


def is_htmx_request() -> bool:
    """Return whether the current request came from HTMX."""
    return request.headers.get("HX-Request") == "true"


@web_bp.before_request
def require_owner_session():
    """Reject unauthenticated requests before any private page runs."""
    token = request.cookies.get(auth_service.AUTH_COOKIE)
    user = auth_service.find_session(token)

    if user is None:
        target = request.full_path
        if target.endswith("?"):
            target = target[:-1]
        login_url = url_for("auth.login", next=target)
        if is_htmx_request():
            response = make_response("", 401)
            response.headers["HX-Redirect"] = login_url
            return response
        return redirect(login_url)

    g.user = user
    g.session_token = token


def render_page(template_name: str, **context):
    """Render a page, trimming the shell for HTMX navigation requests."""
    return render_template(
        template_name,
        htmx_request=is_htmx_request(),
        **context,
    )


@web_bp.get("/")
def dashboard():
    """Render the overview page."""
    return render_page(
        "dashboard.html",
        page_title="Overview",
        page_description="A quiet home for drafts, schedules and results.",
    )


@web_bp.get("/posts")
def posts():
    """Render the posts placeholder."""
    return render_page(
        "posts.html",
        page_title="Posts",
        page_description="Compose once, tailor per platform, publish deliberately.",
    )


@web_bp.get("/calendar")
def calendar():
    """Render a Monday-first week view placeholder."""
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    week_days = [
        {
            "label": (monday + timedelta(days=offset)).strftime("%a"),
            "day": (monday + timedelta(days=offset)).day,
            "date": (monday + timedelta(days=offset)).isoformat(),
            "is_today": (monday + timedelta(days=offset)) == today,
        }
        for offset in range(7)
    ]
    return render_page(
        "calendar.html",
        page_title="Calendar",
        page_description="Schedule in your timezone; store and publish in UTC.",
        week_days=week_days,
        week_label=f"{monday.strftime('%d %b')} – "
        f"{(monday + timedelta(days=6)).strftime('%d %b %Y')}",
    )


@web_bp.get("/accounts")
def accounts():
    """Render the accounts placeholder."""
    platforms = [
        {"name": "Instagram", "icon": "camera", "accent": "rose"},
        {"name": "Facebook", "icon": "thumbs-up", "accent": "blue"},
        {"name": "TikTok", "icon": "music-2", "accent": "slate"},
        {"name": "X", "icon": "at-sign", "accent": "slate"},
        {"name": "YouTube", "icon": "play", "accent": "red"},
    ]
    return render_page(
        "accounts.html",
        page_title="Accounts",
        page_description="Each account chooses its own publishing mode.",
        platforms=platforms,
    )


@web_bp.get("/analytics")
def analytics():
    """Render the analytics placeholder."""
    return render_page(
        "analytics.html",
        page_title="Analytics",
        page_description="Simulated data is always labelled as simulated.",
    )


@web_bp.get("/settings")
def settings():
    """Render read-only application settings."""
    config = current_app.config
    values = [
        ("Application", config["APP_NAME"]),
        ("Version", config["APP_VERSION"]),
        ("Environment", "testing" if config.get("TESTING") else "development"),
        ("Presentation timezone", config["APP_TIMEZONE"]),
        ("Database", config["SQLALCHEMY_DATABASE_URI"]),
        ("Media root", config["MEDIA_ROOT"]),
        (
            "Upload ceiling",
            f"{config['MAX_CONTENT_LENGTH'] // (1024 * 1024)} MiB",
        ),
    ]
    return render_page(
        "settings.html",
        page_title="Settings",
        page_description="Configuration is read from environment variables.",
        settings=values,
    )
