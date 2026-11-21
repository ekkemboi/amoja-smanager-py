"""Route-level tests for sign-in, session guards and sign-out."""

from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
from sqlalchemy import select, update

from src.models import UserSession, db
from src.services.auth import hash_session_token
from tests.helpers import OWNER_PASSWORD, login, logout

PRIVATE_PATHS = ["/", "/posts", "/calendar", "/accounts", "/analytics", "/settings"]


@pytest.mark.parametrize("path", PRIVATE_PATHS)
def test_private_pages_redirect_when_signed_out(client, path):
    """Every private page redirects to sign-in and remembers the target."""
    response = client.get(path)

    assert response.status_code == 302
    location = response.headers["Location"]
    assert location.startswith("/login")
    assert parse_qs(urlsplit(location).query)["next"] == [path]


@pytest.mark.parametrize("path", PRIVATE_PATHS)
def test_htmx_private_pages_receive_a_full_redirect(client, path):
    """An expired HTMX request redirects the whole browser, not just main."""
    response = client.get(path, headers={"HX-Request": "true"})

    assert response.status_code == 401
    assert response.headers["HX-Redirect"].startswith("/login")
    assert response.get_data(as_text=True) == ""


def test_login_page_is_public_and_has_no_shell(client):
    """The sign-in page renders without navigation or a session."""
    response = client.get("/login")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Sign in" in body
    assert 'name="csrf_token"' in body
    assert "<aside" not in body


def test_login_requires_a_csrf_token(client, owner):
    """A cross-site form post cannot attempt a sign-in."""
    response = client.post(
        "/login",
        data={"username": "owner", "password": OWNER_PASSWORD},
    )

    assert response.status_code == 400
    assert client.get_cookie("amoja_session") is None


def test_failed_login_shows_an_error_and_sets_no_cookie(client, owner):
    """Bad credentials do not create a session or leak which part failed."""
    response = login(client, password="incorrect password")

    assert response.status_code == 401
    body = response.get_data(as_text=True)
    assert "Unable to sign in" in body
    assert "incorrect password" not in body
    assert client.get_cookie("amoja_session") is None


def test_successful_login_sets_a_hardened_cookie_and_opens_the_dashboard(client, owner):
    """Sign-in sets an HttpOnly, SameSite=Lax, seven-day cookie."""
    response = login(client, next_path="/accounts")

    assert response.status_code == 302
    assert response.headers["Location"] == "/accounts"
    set_cookie = response.headers["Set-Cookie"]
    assert "amoja_session=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "SameSite=Lax" in set_cookie
    assert "Path=/" in set_cookie
    assert "Max-Age=604800" in set_cookie
    assert "Secure" not in set_cookie  # testing runs over http

    dashboard = client.get("/accounts")
    assert dashboard.status_code == 200
    assert "<h1>Accounts</h1>" in dashboard.get_data(as_text=True)
    assert dashboard.headers["Cache-Control"] == "no-store"


def test_login_persists_across_requests(client, owner):
    """The session cookie authorizes repeated requests."""
    assert login(client).status_code == 302

    assert client.get("/").status_code == 200
    assert client.get("/posts").status_code == 200


def test_logged_in_owner_visiting_login_is_redirected(auth_client):
    """A valid session skips the sign-in form."""
    response = auth_client.get("/login")

    assert response.status_code == 302
    assert response.headers["Location"] == "/"


def test_logout_requires_a_csrf_token(auth_client):
    """A cross-site sign-out is rejected."""
    response = auth_client.post("/logout")

    assert response.status_code == 400
    assert auth_client.get("/").status_code == 200


def test_logout_revokes_the_session_and_clears_the_cookie(auth_client):
    """Sign-out deletes the stored token and returns to the login page."""
    response = logout(auth_client)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")
    assert auth_client.get_cookie("amoja_session") is None
    assert auth_client.get("/").status_code == 302


def test_forged_session_cookie_is_rejected(client, owner):
    """A syntactically valid but unknown token cannot open the dashboard."""
    client.set_cookie("amoja_session", "x" * 43)

    response = client.get("/posts")

    assert response.status_code == 302
    assert response.headers["Location"].startswith("/login")


def test_expired_database_session_is_rejected(auth_client):
    """A token whose row has expired no longer authorizes access."""
    token = auth_client.get_cookie("amoja_session").value
    db.session.execute(
        update(UserSession)
        .where(UserSession.token_hash == hash_session_token(token))
        .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    )
    db.session.commit()

    response = auth_client.get("/accounts")

    assert response.status_code == 302
    assert response.headers["Location"].startswith("/login")


@pytest.mark.parametrize("target", ["//evil.example/path", "https://evil.example"])
def test_unsafe_next_targets_are_ignored(client, owner, target):
    """An open redirect in the next parameter falls back to the dashboard."""
    response = login(client, next_path=target)

    assert response.status_code == 302
    assert response.headers["Location"] == "/"


def test_safe_next_target_is_preserved(client, owner):
    """Local next targets survive sign-in."""
    response = login(client, next_path="/settings?tab=security")

    assert response.status_code == 302
    assert response.headers["Location"] == "/settings?tab=security"


def test_csrf_session_and_auth_cookie_are_separate(client, owner):
    """The CSRF session cookie cannot overwrite the opaque auth cookie."""
    assert login(client).status_code == 302

    csrf_cookie = client.get_cookie("amoja_csrf")
    auth_cookie = client.get_cookie("amoja_session")
    assert csrf_cookie is not None
    assert auth_cookie is not None
    assert csrf_cookie.value != auth_cookie.value
    assert hash_session_token(auth_cookie.value) is not None


def test_session_cookie_value_is_not_stored_in_the_database(auth_client):
    """Only the SHA-256 hash of the cookie value is persisted."""
    token = auth_client.get_cookie("amoja_session").value
    rows = (
        db.session.execute(
            select(UserSession).where(
                UserSession.token_hash == hash_session_token(token)
            )
        )
        .scalars()
        .all()
    )

    assert len(rows) == 1
    assert rows[0].token_hash != token
