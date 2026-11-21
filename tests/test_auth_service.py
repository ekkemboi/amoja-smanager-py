"""Unit tests for password, session and lockout behaviour."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update

from src.models import User, UserSession, db
from src.services import auth
from tests.helpers import OWNER_PASSWORD, OWNER_USERNAME


def test_password_hashes_use_independent_salts(app):
    """The same password hashes differently and verifies correctly."""
    first = auth.hash_password("correct horse battery staple")
    second = auth.hash_password("correct horse battery staple")

    assert first != second
    assert "correct horse battery staple" not in first
    assert auth.verify_password("correct horse battery staple", first) is True
    assert auth.verify_password("wrong", first) is False
    assert auth.verify_password("correct horse battery staple", "malformed") is False
    assert auth.verify_password("x", None) is False


def test_session_tokens_are_random_hashed_and_validated(app):
    """Tokens are 256-bit, stored hashed, and malformed cookies are ignored."""
    token = auth.new_session_token()
    other = auth.new_session_token()

    assert len(token) == 43
    assert token != other
    token_hash = auth.hash_session_token(token)
    assert token_hash is not None
    assert len(token_hash) == 64
    assert token_hash != token
    assert auth.hash_session_token("bad cookie") is None
    assert auth.hash_session_token(None) is None


def test_owner_credentials_are_normalized_and_bounded(app):
    """Usernames normalize and passwords stay within their bounds."""
    assert auth.validate_owner_credentials(" OWNER ", "a" * 12) == "owner"
    assert auth.validate_login(" OWNER ", " a ") == "owner"

    with pytest.raises(auth.AuthValidationError):
        auth.validate_owner_credentials("ab", "a" * 12)
    with pytest.raises(auth.AuthValidationError):
        auth.validate_owner_credentials("bad name", "a" * 12)
    with pytest.raises(auth.AuthValidationError):
        auth.validate_owner_credentials("owner", "short")
    with pytest.raises(auth.AuthValidationError):
        auth.validate_owner_credentials("owner", "x" * 129)

    assert auth.validate_login("bad name", "password") is None
    assert auth.validate_login("owner", "") is None
    assert auth.validate_login("owner", "x" * 129) is None


def test_provision_owner_is_idempotent(app):
    """Only the first provisioning creates the owner."""
    assert auth.provision_owner(OWNER_USERNAME, OWNER_PASSWORD) is True

    original = db.session.get(User, "owner")
    original_hash = original.password_hash

    assert auth.provision_owner("other", "another long password") is False
    refreshed = db.session.get(User, "owner")
    assert refreshed.username == OWNER_USERNAME
    assert refreshed.password_hash == original_hash


def test_authenticate_issues_a_hashed_session(app, owner):
    """A valid login stores only a hash and resets the failure budget."""
    owner.failed_attempts = 3
    db.session.commit()

    ticket = auth.authenticate(OWNER_USERNAME, OWNER_PASSWORD)

    assert ticket is not None
    assert ticket.expires_at > datetime.now(UTC)
    sessions = db.session.execute(select(UserSession)).scalars().all()
    assert len(sessions) == 1
    assert sessions[0].token_hash == auth.hash_session_token(ticket.token)
    assert sessions[0].token_hash != ticket.token
    assert db.session.get(User, "owner").failed_attempts == 0
    assert auth.find_session(ticket.token).username == OWNER_USERNAME


def test_wrong_password_increments_failures_without_a_session(app, owner):
    """Failures persist and do not create a session."""
    for expected in range(1, 5):
        ticket = auth.authenticate(OWNER_USERNAME, "incorrect password")
        assert ticket is None
        assert db.session.get(User, "owner").failed_attempts == expected

    assert db.session.execute(select(UserSession)).scalars().all() == []


def test_fifth_failure_locks_even_the_correct_password(app, owner):
    """Five failures lock sign-in for fifteen minutes."""
    now = datetime.now(UTC)
    for _ in range(4):
        auth.authenticate(OWNER_USERNAME, "incorrect password", now=now)
    auth.authenticate(OWNER_USERNAME, "incorrect password", now=now)

    user = db.session.get(User, "owner")
    assert user.failed_attempts == 5
    assert user.locked_until is not None
    assert auth.authenticate(OWNER_USERNAME, OWNER_PASSWORD, now=now) is None
    assert (
        auth.authenticate(
            OWNER_USERNAME, OWNER_PASSWORD, now=now + timedelta(minutes=16)
        )
        is not None
    )


def test_failure_budget_resets_after_lockout_expires(app, owner):
    """After a lockout expires, the next failure starts the budget again."""
    now = datetime.now(UTC)
    for _ in range(5):
        auth.authenticate(OWNER_USERNAME, "incorrect password", now=now)

    later = now + timedelta(minutes=16)
    assert auth.authenticate(OWNER_USERNAME, "incorrect password", now=later) is None

    user = db.session.get(User, "owner")
    assert user.failed_attempts == 1
    assert user.locked_until is None


def test_malformed_login_does_not_consume_the_failure_budget(app, owner):
    """Invalid input is rejected before touching the owner row."""
    assert auth.authenticate(OWNER_USERNAME, "x" * 129) is None
    assert db.session.get(User, "owner").failed_attempts == 0


def test_login_rotates_the_previous_session(app, owner):
    """A second login revokes the previous token and keeps one session."""
    first = auth.authenticate(OWNER_USERNAME, OWNER_PASSWORD)
    assert first is not None

    second = auth.authenticate(
        OWNER_USERNAME, OWNER_PASSWORD, previous_token=first.token
    )
    assert second is not None
    assert auth.find_session(first.token) is None
    assert auth.find_session(second.token).username == OWNER_USERNAME

    sessions = db.session.execute(select(UserSession)).scalars().all()
    assert len(sessions) == 1


def test_expired_sessions_are_purged_on_login(app, owner):
    """Login removes expired session rows."""
    expired_hash = "a" * 64
    db.session.add(
        UserSession(
            token_hash=expired_hash,
            user_id="owner",
            expires_at=datetime.now(UTC) - timedelta(minutes=1),
        )
    )
    db.session.commit()

    assert auth.authenticate(OWNER_USERNAME, OWNER_PASSWORD) is not None
    remaining = db.session.execute(
        select(UserSession).where(UserSession.token_hash == expired_hash)
    ).scalar_one_or_none()
    assert remaining is None


def test_sessions_expire_and_revoke(app, owner):
    """Expired tokens fail lookups and revocation removes the row."""
    ticket = auth.authenticate(OWNER_USERNAME, OWNER_PASSWORD)
    assert ticket is not None

    later = datetime.now(UTC) + timedelta(seconds=auth.SESSION_SECONDS + 1)
    assert auth.find_session(ticket.token, now=later) is None

    auth.revoke_session(ticket.token)
    assert auth.find_session(ticket.token) is None
    assert db.session.execute(select(UserSession)).scalars().all() == []


def test_expired_session_rows_remain_readable(app, owner):
    """SQLite returns naive datetimes; sessions still compare correctly."""
    ticket = auth.authenticate(OWNER_USERNAME, OWNER_PASSWORD)
    token_hash = auth.hash_session_token(ticket.token)

    db.session.execute(
        update(UserSession)
        .where(UserSession.token_hash == token_hash)
        .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    )
    db.session.commit()

    assert auth.find_session(ticket.token) is None
