"""Flask application factory for Amoja Social Manager."""

import os
from datetime import UTC, datetime
from pathlib import Path

from flask import Flask, g, request
from flask_wtf.csrf import CSRFProtect

from src.cli import register_cli
from src.config import config
from src.models import db
from web.navigation import NAV_ITEMS


def create_app(config_name=None):
    """Create and configure the Flask application."""
    if config_name is None:
        config_name = os.environ.get("FLASK_ENV", "development")

    app = Flask(
        __name__,
        template_folder="../web/templates",
        static_folder="../web/static",
    )
    app.config.from_object(config[config_name]())
    app.secret_key = app.config["SECRET_KEY"]

    _ensure_instance_directories(app)

    db.init_app(app)

    csrf = CSRFProtect()
    csrf.init_app(app)

    @app.after_request
    def add_security_headers(response):
        """Apply baseline security headers to every response."""
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' "
            "https://cdn.tailwindcss.com https://cdn.jsdelivr.net "
            "https://unpkg.com; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com "
            "https://cdn.tailwindcss.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: https:; "
            "connect-src 'self';"
        )
        if not app.config.get("DEBUG"):
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        if request.path in ("/login", "/logout") or g.get("user") is not None:
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/healthz")
    def healthz():
        """Report a lightweight liveness check."""
        return {
            "status": "ok",
            "service": "amoja-smanager",
            "version": app.config["APP_VERSION"],
        }

    @app.context_processor
    def inject_template_globals():
        """Expose shared navigation and branding to every template."""
        return {
            "app_name": app.config["APP_NAME"],
            "app_version": app.config["APP_VERSION"],
            "app_timezone": app.config["APP_TIMEZONE"],
            "nav_items": NAV_ITEMS,
            "current_path": request.path,
            "current_year": datetime.now(UTC).year,
            "current_user": g.get("user"),
        }

    from web.routes import web_bp
    from web.routes.auth import auth_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(web_bp)
    register_cli(app)

    if app.config.get("TESTING"):
        with app.app_context():
            db.create_all()

    return app


def _ensure_instance_directories(app):
    """Create the instance, media and SQLite parent directories."""
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    Path(app.config["MEDIA_ROOT"]).mkdir(parents=True, exist_ok=True)

    uri = app.config["SQLALCHEMY_DATABASE_URI"]
    if not uri.startswith("sqlite:///"):
        return
    path = uri.removeprefix("sqlite:///")
    if not path or path == ":memory:":
        return
    database_path = Path(path)
    if not database_path.is_absolute():
        database_path = Path.cwd() / database_path
    database_path.parent.mkdir(parents=True, exist_ok=True)


if __name__ == "__main__":
    application = create_app()
    application.run(debug=True, host="127.0.0.1", port=5001)
