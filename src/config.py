"""Configuration for Amoja Social Manager."""

import os
from pathlib import Path


class Config:
    """Base configuration shared by every environment."""

    BASE_DIR = Path(__file__).resolve().parent.parent
    INSTANCE_DIR = BASE_DIR / "instance"
    DEFAULT_SQLITE_PATH = INSTANCE_DIR / "amoja-smanager.db"

    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{DEFAULT_SQLITE_PATH}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Presentation defaults. Timestamps are stored in UTC; this zone is for display.
    APP_TIMEZONE = os.environ.get("APP_TIMEZONE", "UTC")

    # Private media storage. A storage abstraction replaces this later.
    MEDIA_ROOT = os.environ.get("MEDIA_ROOT", str(INSTANCE_DIR / "media"))

    # 100 MiB covers the largest permitted video upload.
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_CONTENT_LENGTH", 100 * 1024 * 1024))

    # Flask's CSRF session cookie and the separate opaque auth cookie.
    # Secure is required over HTTPS in production.
    SESSION_COOKIE_NAME = "amoja_csrf"
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_SAMESITE = "Lax"
    AUTH_COOKIE_SECURE = True
    AUTH_COOKIE_SAMESITE = "Lax"

    APP_NAME = "Amoja Social"
    APP_VERSION = "0.1.0"


class DevelopmentConfig(Config):
    """Local development configuration."""

    DEBUG = True
    SESSION_COOKIE_SECURE = False
    AUTH_COOKIE_SECURE = False


class TestingConfig(Config):
    """Test configuration using a disposable in-memory database."""

    TESTING = True
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///:memory:")
    MEDIA_ROOT = os.environ.get("MEDIA_ROOT", "/tmp/amoja-smanager-test-media")
    SESSION_COOKIE_SECURE = False
    AUTH_COOKIE_SECURE = False


class ProductionConfig(Config):
    """Production configuration that refuses to start without a secret."""

    DEBUG = False

    def __init__(self):
        """Validate required production settings."""
        super().__init__()
        secret = os.environ.get("SECRET_KEY")
        if not secret or not secret.strip():
            raise ValueError(
                "SECRET_KEY environment variable must be set in production"
            )
        self.SECRET_KEY = secret


config = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
