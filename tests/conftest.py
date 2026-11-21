"""Test fixtures for Amoja Social Manager."""

import pytest

from src.app import create_app
from src.models import User
from src.models import db as _db
from src.services.auth import provision_owner
from tests.helpers import OWNER_PASSWORD, OWNER_USERNAME, login


@pytest.fixture(scope="function")
def app():
    """Create a testing application with a fresh in-memory database."""
    application = create_app("testing")
    with application.app_context():
        yield application
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def client(app):
    """Create a Flask test client."""
    return app.test_client()


@pytest.fixture
def owner(app):
    """Provision the single owner account."""
    assert provision_owner(OWNER_USERNAME, OWNER_PASSWORD) is True
    return _db.session.get(User, "owner")


@pytest.fixture
def auth_client(client, owner):
    """Return a client already signed in as the owner."""
    response = login(client)
    assert response.status_code == 302
    return client
