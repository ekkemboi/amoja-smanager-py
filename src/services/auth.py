"""Authentication service: passwords, sessions and the single owner."""

import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from src.models import User, UserSession, db

AUTH_COOKIE = "amoja_session"
SESSION_SECONDS = 7 * 24 * 60 * 60

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_SECONDS = 15 * 60

# Deliberately expensive: about 128 MiB and a fraction of a second per hash.
_SCRYPT_N = 2**17
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_MAXMEM = 192 * 1024 * 1024
_SCRYPT_DKLEN = 64

_USERNAME_RE = re.compile(r"^[a-z0-9_.-]{3,64}$")
_PASSWORD_HASH_RE = re.compile(r"^scrypt-v1:([a-f0-9]{32}):([a-f0-9]{128})$")
_SESSION_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{43}$")


class AuthValidationError(ValueError):
    """Raised when owner or login credentials fail validation."""


@dataclass(frozen=True)
class SessionTicket:
    """A newly issued session token and its expiry."""

    token: str
    expires_at: datetime


def _derive(password: str, salt_hex: str) -> bytes:
    """Derive a scrypt key from a password and hexadecimal salt."""
    return hashlib.scrypt(
        password.encode("utf-8"),
        salt=bytes.fromhex(salt_hex),
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        maxmem=_SCRYPT_MAXMEM,
        dklen=_SCRYPT_DKLEN,
    )


def hash_password(password: str) -> str:
    """Hash a password with a fresh random salt."""
    salt = secrets.token_hex(16)
    key = _derive(password, salt)
    return f"scrypt-v1:{salt}:{key.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    """Verify a password against a stored scrypt hash."""
    if not isinstance(password, str) or not isinstance(encoded, str):
        return False
    match = _PASSWORD_HASH_RE.fullmatch(encoded)
    if match is None:
        return False
    try:
        actual = _derive(password, match.group(1))
    except (ValueError, MemoryError):
        return False
    return hmac.compare_digest(actual, bytes.fromhex(match.group(2)))


def new_session_token() -> str:
    """Return a new opaque 256-bit session token."""
    return secrets.token_urlsafe(32)


def hash_session_token(token: str | None) -> str | None:
    """Hash a session token for storage, rejecting malformed cookies."""
    if not isinstance(token, str) or _SESSION_TOKEN_RE.fullmatch(token) is None:
        return None
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def normalize_username(value: str | None) -> str:
    """Trim and lowercase a username."""
    if not isinstance(value, str):
        return ""
    return value.strip().lower()


def validate_owner_credentials(username: str | None, password: str | None) -> str:
    """Validate owner credentials and return the normalized username."""
    normalized = normalize_username(username)
    if _USERNAME_RE.fullmatch(normalized) is None:
        raise AuthValidationError(
            "Choose a username of 3-64 lowercase letters, digits, dots, dashes "
            "or underscores."
        )
    if not isinstance(password, str) or not 12 <= len(password) <= 128:
        raise AuthValidationError("Choose a password of 12-128 characters.")
    return normalized


def validate_login(username: str | None, password: str | None) -> str | None:
    """Validate login input, returning the normalized username or None."""
    normalized = normalize_username(username)
    if _USERNAME_RE.fullmatch(normalized) is None:
        return None
    if not isinstance(password, str) or not 1 <= len(password) <= 128:
        return None
    return normalized


def provision_owner(username: str | None, password: str | None) -> bool:
    """Create the single owner account. Return False if it already exists."""
    normalized = validate_owner_credentials(username, password)
    if db.session.get(User, "owner") is not None:
        return False

    db.session.add(
        User(
            id="owner",
            username=normalized,
            password_hash=hash_password(password),
        )
    )
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return False
    return True


def _begin_immediate() -> None:
    """Serialize an auth attempt with SQLite's write lock.

    SQLite has no ``SELECT ... FOR UPDATE``. ``BEGIN IMMEDIATE`` takes the
    database write lock before the row is read, so concurrent failed attempts
    cannot both consume the same failure slot.
    """
    db.session.rollback()
    connection = db.session.connection()
    if connection.dialect.name == "sqlite":
        connection.exec_driver_sql("BEGIN IMMEDIATE")


def _as_utc(value: datetime | None) -> datetime | None:
    """Normalize a SQLite datetime (which loses its offset) to UTC."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def authenticate(
    username: str | None,
    password: str | None,
    previous_token: str | None = None,
    now: datetime | None = None,
) -> SessionTicket | None:
    """Authenticate the owner and issue a rotated session.

    Returns None for invalid credentials, a locked owner or malformed input.
    """
    normalized = validate_login(username, password)
    if normalized is None:
        return None

    now = now or datetime.now(UTC)
    _begin_immediate()
    try:
        owner = db.session.get(User, "owner")
        if owner is None:
            db.session.rollback()
            return None

        locked_until = _as_utc(owner.locked_until)
        if locked_until is not None and locked_until > now:
            db.session.rollback()
            return None

        password_ok = verify_password(password, owner.password_hash)
        if not password_ok or normalized != owner.username:
            failures = (
                1 if owner.locked_until is not None else owner.failed_attempts + 1
            )
            owner.failed_attempts = failures
            owner.locked_until = (
                now + timedelta(seconds=LOCKOUT_SECONDS)
                if failures >= MAX_FAILED_ATTEMPTS
                else None
            )
            db.session.commit()
            return None

        owner.failed_attempts = 0
        owner.locked_until = None

        previous_hash = hash_session_token(previous_token)
        if previous_hash is not None:
            db.session.execute(
                delete(UserSession).where(UserSession.token_hash == previous_hash)
            )
        db.session.execute(delete(UserSession).where(UserSession.expires_at <= now))

        token = new_session_token()
        expires_at = now + timedelta(seconds=SESSION_SECONDS)
        db.session.add(
            UserSession(
                token_hash=hash_session_token(token),
                user_id=owner.id,
                expires_at=expires_at,
            )
        )
        db.session.commit()
        return SessionTicket(token=token, expires_at=expires_at)
    except Exception:
        db.session.rollback()
        raise


def find_session(token: str | None, now: datetime | None = None) -> User | None:
    """Return the owner for a valid unexpired session token."""
    token_hash = hash_session_token(token)
    if token_hash is None:
        return None

    now = now or datetime.now(UTC)
    statement = (
        select(User)
        .join(UserSession, UserSession.user_id == User.id)
        .where(
            UserSession.token_hash == token_hash,
            UserSession.expires_at > now,
        )
        .limit(1)
    )
    return db.session.execute(statement).scalars().first()


def revoke_session(token: str | None) -> None:
    """Delete the session row for a token, if it exists."""
    token_hash = hash_session_token(token)
    if token_hash is None:
        return
    db.session.execute(delete(UserSession).where(UserSession.token_hash == token_hash))
    db.session.commit()
