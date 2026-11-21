"""Shared test helpers for authentication flows."""

import re

OWNER_USERNAME = "owner"
OWNER_PASSWORD = "correct horse battery staple"

_CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')


def csrf_token(client, path="/login"):
    """Fetch a page and return its CSRF token."""
    body = client.get(path).get_data(as_text=True)
    match = _CSRF_RE.search(body)
    assert match is not None, f"No CSRF token on {path}"
    return match.group(1)


def login(client, username=OWNER_USERNAME, password=OWNER_PASSWORD, next_path="/"):
    """Submit the sign-in form with a valid CSRF token."""
    return client.post(
        "/login",
        data={
            "csrf_token": csrf_token(client, "/login"),
            "username": username,
            "password": password,
            "next": next_path,
        },
    )


def logout(client):
    """Submit the sign-out form with a valid CSRF token."""
    return client.post(
        "/logout",
        data={"csrf_token": csrf_token(client, "/")},
    )
