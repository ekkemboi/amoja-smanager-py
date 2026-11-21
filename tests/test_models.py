"""Schema smoke tests for the SQLite data model."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from src.models import (
    AnalyticsSnapshot,
    AnalyticsSource,
    Media,
    MediaKind,
    Post,
    PostTarget,
    PublishAttempt,
    PublishJob,
    SocialAccount,
    SocialPlatform,
    User,
    UserSession,
    db,
)


def _make_account(handle="amoja"):
    return SocialAccount(
        platform=SocialPlatform.INSTAGRAM,
        handle=handle,
        display_name="Amoja",
    )


def test_schema_persists_a_publishing_graph(app):
    """A full post, target, job, attempt and snapshot round-trips."""
    now = datetime.now(UTC)

    account = _make_account()
    post = Post(body="Hello from the skeleton")
    db.session.add_all([account, post])
    db.session.flush()

    target = PostTarget(
        post_id=post.id,
        account_id=account.id,
        platform=SocialPlatform.INSTAGRAM,
        content="Instagram variant",
    )
    db.session.add(target)
    db.session.flush()

    media = Media(
        post_id=post.id,
        position=0,
        kind=MediaKind.IMAGE,
        storage_key="media/one.png",
        mime_type="image/png",
        byte_size=1024,
        width=1080,
        height=1080,
    )
    job = PublishJob(target_id=target.id, due_at=now)
    db.session.add_all([media, job])
    db.session.flush()

    attempt = PublishAttempt(
        job_id=job.id,
        attempt_number=1,
        mode=job.target.account.mode,
        simulated=True,
    )
    snapshot = AnalyticsSnapshot(
        account_id=account.id,
        metric="followers",
        value=42,
        source=AnalyticsSource.MOCK,
        simulated=True,
        observed_at=now,
    )
    db.session.add_all([attempt, snapshot])
    db.session.commit()

    assert db.session.get(Post, post.id).body == "Hello from the skeleton"
    assert db.session.get(PostTarget, target.id).platform == SocialPlatform.INSTAGRAM
    assert db.session.get(PublishJob, job.id).status.value == "pending"
    assert db.session.get(PublishAttempt, attempt.id).simulated is True
    assert db.session.get(AnalyticsSnapshot, snapshot.id).value == 42
    assert db.session.get(Media, media.id).mime_type == "image/png"


def test_duplicate_platform_handle_is_rejected(app):
    """The same handle cannot exist twice on one platform."""
    db.session.add(_make_account("amoja"))
    db.session.commit()

    db.session.add(_make_account("amoja"))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_single_owner_constraint_is_enforced(app):
    """Only the fixed 'owner' user row is allowed."""
    db.session.add(User(id="owner", username="owner", password_hash="hashed"))
    db.session.commit()

    db.session.add(User(id="intruder", username="other", password_hash="hashed"))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_analytics_requires_a_subject(app):
    """A snapshot must point at an account or a target."""
    snapshot = AnalyticsSnapshot(
        metric="impressions",
        value=1,
        source=AnalyticsSource.MOCK,
        simulated=True,
        observed_at=datetime.now(UTC),
    )
    db.session.add(snapshot)

    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_mock_provenance_cannot_claim_live_data(app):
    """The check constraint keeps source and simulated flag consistent."""
    owner = User(id="owner", username="owner", password_hash="hashed")
    account = _make_account()
    db.session.add_all([owner, account])
    db.session.flush()

    snapshot = AnalyticsSnapshot(
        account_id=account.id,
        metric="followers",
        value=10,
        source=AnalyticsSource.MOCK,
        simulated=False,
        observed_at=datetime.now(UTC),
    )
    db.session.add(snapshot)

    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_sessions_cascade_with_the_owner(app):
    """Deleting the owner removes its sessions."""
    owner = User(id="owner", username="owner", password_hash="hashed")
    db.session.add(owner)
    db.session.flush()

    session = UserSession(
        token_hash="a" * 64,
        user_id=owner.id,
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    db.session.add(session)
    db.session.commit()

    db.session.delete(owner)
    db.session.commit()

    assert db.session.get(UserSession, "a" * 64) is None
