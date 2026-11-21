"""Smoke tests for the dashboard shell."""

import pytest

from src.app import create_app

PAGES = [
    ("/", "Overview"),
    ("/posts", "Posts"),
    ("/calendar", "Calendar"),
    ("/accounts", "Accounts"),
    ("/analytics", "Analytics"),
    ("/settings", "Settings"),
]


@pytest.mark.parametrize(("path", "heading"), PAGES)
def test_page_renders(auth_client, path, heading):
    """Every dashboard page renders its heading for the owner."""
    response = auth_client.get(path)

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert f"<h1>{heading}</h1>" in body
    assert "Amoja Social" in body


@pytest.mark.parametrize(("path", "heading"), PAGES)
def test_page_renders_without_shell_for_htmx(auth_client, path, heading):
    """HTMX responses omit the sidebar and keep the content target."""
    response = auth_client.get(path, headers={"HX-Request": "true"})

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert f"<h1>{heading}</h1>" in body
    assert 'id="page-content"' in body
    assert "<aside" not in body


def test_sidebar_lists_every_section(auth_client):
    """The full page includes navigation for each section."""
    body = auth_client.get("/").get_data(as_text=True)

    for href in ("/posts", "/calendar", "/accounts", "/analytics", "/settings"):
        assert f'href="{href}"' in body
    assert "hx-get=" in body
    assert 'aria-current="page"' in body


def test_sidebar_shows_owner_and_sign_out(auth_client):
    """The shell identifies the owner and offers a sign-out form."""
    body = auth_client.get("/").get_data(as_text=True)

    assert "owner" in body
    assert "Sign out" in body
    assert 'action="/logout"' in body
    assert 'name="csrf_token"' in body


def test_healthz_reports_ok(client):
    """The liveness endpoint is public and returns a small JSON payload."""
    response = client.get("/healthz")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "ok"
    assert payload["service"] == "amoja-smanager"


def test_security_headers_are_present(auth_client):
    """Baseline response headers are applied."""
    response = auth_client.get("/")

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "default-src 'self'" in response.headers["Content-Security-Policy"]
    assert response.headers["Cache-Control"] == "no-store"


def test_htmx_navigation_attributes_are_used(auth_client):
    """Sidebar links opt into fragment swaps instead of full reloads."""
    body = auth_client.get("/").get_data(as_text=True)

    assert 'hx-target="#page-content"' in body
    assert 'hx-select="#page-content"' in body
    assert 'hx-swap="outerHTML"' in body
    assert 'hx-push-url="true"' in body


def test_settings_never_render_a_secret(auth_client, app):
    """Settings exposes configuration names but never the secret value."""
    app.config["SECRET_KEY"] = "super-secret-value"
    body = auth_client.get("/settings").get_data(as_text=True)

    assert "SECRET_KEY" in body
    assert "super-secret-value" not in body


def test_production_requires_a_secret(monkeypatch):
    """Production configuration refuses to start without SECRET_KEY."""
    monkeypatch.delenv("SECRET_KEY", raising=False)

    with pytest.raises(ValueError, match="SECRET_KEY"):
        create_app("production")
