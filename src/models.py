"""SQLAlchemy models for Amoja Social Manager.

The schema mirrors the TypeScript implementation's data model. SQLite is used
for the single-user skeleton; enum values, checks and indexes are kept portable
so the same schema can move to PostgreSQL later.
"""

import sqlite3
import uuid
from datetime import UTC, datetime
from enum import StrEnum

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event
from sqlalchemy.engine import Engine

db = SQLAlchemy()


@event.listens_for(Engine, "connect")
def _configure_sqlite(dbapi_connection, connection_record):
    """Enable SQLite integrity and concurrency pragmas on every connection."""
    if not isinstance(dbapi_connection, sqlite3.Connection):
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


def utcnow() -> datetime:
    """Return the current timezone-aware UTC time."""
    return datetime.now(UTC)


def new_id() -> str:
    """Return a new UUID string for a primary key."""
    return str(uuid.uuid4())


def _enum(enum_cls, name: str):
    """Build a stored-as-value enum column type with a check constraint."""
    return db.Enum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        values_callable=lambda members: [member.value for member in members],
    )


class SocialPlatform(StrEnum):
    """Platforms the manager can target."""

    INSTAGRAM = "instagram"
    FACEBOOK = "facebook"
    TIKTOK = "tiktok"
    TWITTER = "twitter"
    YOUTUBE = "youtube"


class PublishingMode(StrEnum):
    """How a target is published for a given account."""

    MOCK = "mock"
    API = "api"
    BROWSER = "browser"
    MANUAL = "manual"


class ConnectionStatus(StrEnum):
    """Connection state of a social account."""

    UNCONFIGURED = "unconfigured"
    CONNECTED = "connected"
    EXPIRED = "expired"
    DISCONNECTED = "disconnected"


class PostStatus(StrEnum):
    """Aggregate status of a post."""

    DRAFT = "draft"
    SCHEDULED = "scheduled"
    PUBLISHING = "publishing"
    PUBLISHED = "published"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELED = "canceled"
    PENDING_MANUAL = "pending_manual"


class TargetStatus(StrEnum):
    """Status of one post variant for one account."""

    DRAFT = "draft"
    SCHEDULED = "scheduled"
    PUBLISHING = "publishing"
    PUBLISHED = "published"
    PENDING_MANUAL = "pending_manual"
    FAILED = "failed"
    UNCERTAIN = "uncertain"
    CANCELED = "canceled"


class JobStatus(StrEnum):
    """Status of a publish job."""

    PENDING = "pending"
    LEASED = "leased"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNCERTAIN = "uncertain"
    CANCELED = "canceled"
    PENDING_MANUAL = "pending_manual"


class AttemptStatus(StrEnum):
    """Status of a single publish attempt."""

    RUNNING = "running"
    PUBLISHED = "published"
    PENDING_MANUAL = "pending_manual"
    FAILED = "failed"
    UNCERTAIN = "uncertain"


class MediaKind(StrEnum):
    """Kind of uploaded media."""

    IMAGE = "image"
    VIDEO = "video"


class AnalyticsSource(StrEnum):
    """Provenance of an analytics observation."""

    MOCK = "mock"
    API = "api"


class User(db.Model):
    """Private single-owner application login."""

    __tablename__ = "users"

    id = db.Column(db.String(16), primary_key=True, default="owner")
    username = db.Column(db.String(255), nullable=False, unique=True)
    password_hash = db.Column(db.String(255), nullable=False)
    failed_attempts = db.Column(db.Integer, nullable=False, default=0)
    locked_until = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    __table_args__ = (
        db.CheckConstraint("id = 'owner'", name="single_owner"),
        db.CheckConstraint("failed_attempts >= 0", name="valid_failed_attempts"),
    )

    def to_dict(self):
        """Return safe public fields."""
        return {
            "id": self.id,
            "username": self.username,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        """Return a debug representation."""
        return f"<User {self.username}>"


class UserSession(db.Model):
    """Hashed opaque session token for the owner."""

    __tablename__ = "sessions"

    token_hash = db.Column(db.String(64), primary_key=True)
    user_id = db.Column(
        db.String(16),
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    __table_args__ = (db.Index("sessions_expiry_idx", "expires_at"),)

    def __repr__(self):
        """Return a debug representation."""
        return f"<UserSession expires_at={self.expires_at}>"


class SocialAccount(db.Model):
    """A social platform account selected by the owner."""

    __tablename__ = "social_accounts"

    id = db.Column(db.String(36), primary_key=True, default=new_id)
    platform = db.Column(_enum(SocialPlatform, "social_platform"), nullable=False)
    handle = db.Column(db.String(255), nullable=False)
    display_name = db.Column(db.String(255), nullable=True)
    external_account_id = db.Column(db.String(255), nullable=True)
    mode = db.Column(
        _enum(PublishingMode, "publishing_mode"),
        nullable=False,
        default=PublishingMode.MOCK,
    )
    connection_status = db.Column(
        _enum(ConnectionStatus, "connection_status"),
        nullable=False,
        default=ConnectionStatus.UNCONFIGURED,
    )
    encrypted_credentials = db.Column(db.Text, nullable=True)
    credentials_updated_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    __table_args__ = (
        db.UniqueConstraint(
            "platform", "handle", name="social_accounts_platform_handle_unique"
        ),
        db.UniqueConstraint(
            "id", "platform", name="social_accounts_id_platform_unique"
        ),
        db.Index(
            "social_accounts_external_id_idx",
            "platform",
            "external_account_id",
            unique=True,
            sqlite_where=db.text("external_account_id IS NOT NULL"),
        ),
        db.CheckConstraint(
            "length(trim(handle)) > 0", name="social_accounts_handle_not_blank"
        ),
        db.CheckConstraint(
            "(encrypted_credentials IS NULL) = (credentials_updated_at IS NULL)",
            name="social_accounts_credentials_pairing",
        ),
    )

    targets = db.relationship("PostTarget", back_populates="account", lazy=True)

    def to_dict(self):
        """Return account fields without credentials."""
        return {
            "id": self.id,
            "platform": self.platform.value
            if isinstance(self.platform, SocialPlatform)
            else self.platform,
            "handle": self.handle,
            "display_name": self.display_name,
            "mode": self.mode.value
            if isinstance(self.mode, PublishingMode)
            else self.mode,
            "connection_status": self.connection_status.value
            if isinstance(self.connection_status, ConnectionStatus)
            else self.connection_status,
        }

    def __repr__(self):
        """Return a debug representation."""
        return f"<SocialAccount {self.platform}:{self.handle}>"


class Post(db.Model):
    """A post and its shared body."""

    __tablename__ = "posts"

    id = db.Column(db.String(36), primary_key=True, default=new_id)
    body = db.Column(db.Text, nullable=False, default="")
    status = db.Column(
        _enum(PostStatus, "post_status"),
        nullable=False,
        default=PostStatus.DRAFT,
    )
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    __table_args__ = (db.Index("posts_status_idx", "status", "updated_at"),)

    media = db.relationship(
        "Media",
        back_populates="post",
        cascade="all, delete-orphan",
        order_by="Media.position",
        lazy=True,
    )
    targets = db.relationship(
        "PostTarget",
        back_populates="post",
        cascade="all, delete-orphan",
        lazy=True,
    )

    def to_dict(self):
        """Return post summary fields."""
        return {
            "id": self.id,
            "body": self.body,
            "status": self.status.value
            if isinstance(self.status, PostStatus)
            else self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        """Return a debug representation."""
        return f"<Post {self.id} status={self.status}>"


class Media(db.Model):
    """Uploaded image or video attached to a post."""

    __tablename__ = "media"

    id = db.Column(db.String(36), primary_key=True, default=new_id)
    post_id = db.Column(
        db.String(36),
        db.ForeignKey("posts.id", ondelete="CASCADE"),
        nullable=False,
    )
    position = db.Column(db.Integer, nullable=False, default=0)
    kind = db.Column(_enum(MediaKind, "media_kind"), nullable=False)
    storage_key = db.Column(db.String(512), nullable=False, unique=True)
    mime_type = db.Column(db.String(127), nullable=False)
    byte_size = db.Column(db.BigInteger, nullable=False)
    width = db.Column(db.Integer, nullable=True)
    height = db.Column(db.Integer, nullable=True)
    duration_ms = db.Column(db.Integer, nullable=True)
    alt_text = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    __table_args__ = (
        db.UniqueConstraint("post_id", "position", name="media_post_position_unique"),
        db.CheckConstraint("byte_size > 0", name="media_byte_size_positive"),
        db.CheckConstraint("position >= 0", name="media_position_non_negative"),
        db.CheckConstraint("width IS NULL OR width > 0", name="media_width_positive"),
        db.CheckConstraint(
            "height IS NULL OR height > 0", name="media_height_positive"
        ),
        db.CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0",
            name="media_duration_non_negative",
        ),
        db.CheckConstraint(
            "kind <> 'video' OR duration_ms IS NOT NULL",
            name="media_video_duration",
        ),
    )

    post = db.relationship("Post", back_populates="media")

    def __repr__(self):
        """Return a debug representation."""
        return f"<Media {self.storage_key}>"


class PostTarget(db.Model):
    """One post variant aimed at one social account."""

    __tablename__ = "post_targets"

    id = db.Column(db.String(36), primary_key=True, default=new_id)
    post_id = db.Column(
        db.String(36),
        db.ForeignKey("posts.id", ondelete="CASCADE"),
        nullable=False,
    )
    account_id = db.Column(db.String(36), nullable=False)
    platform = db.Column(_enum(SocialPlatform, "social_platform"), nullable=False)
    content = db.Column(db.Text, nullable=False, default="")
    status = db.Column(
        _enum(TargetStatus, "target_status"),
        nullable=False,
        default=TargetStatus.DRAFT,
    )
    scheduled_at = db.Column(db.DateTime(timezone=True), nullable=True)
    idempotency_key = db.Column(
        db.String(36), nullable=False, unique=True, default=new_id
    )
    external_post_id = db.Column(db.String(255), nullable=True)
    external_url = db.Column(db.Text, nullable=True)
    published_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    __table_args__ = (
        db.UniqueConstraint(
            "post_id", "account_id", name="post_targets_post_account_unique"
        ),
        db.ForeignKeyConstraint(
            ["account_id", "platform"],
            ["social_accounts.id", "social_accounts.platform"],
            name="post_targets_account_platform_fk",
            ondelete="RESTRICT",
        ),
        db.Index("post_targets_due_idx", "status", "scheduled_at"),
        db.Index("post_targets_account_idx", "account_id"),
        db.CheckConstraint(
            "status NOT IN ('scheduled', 'publishing') OR scheduled_at IS NOT NULL",
            name="post_targets_schedule_required",
        ),
        db.CheckConstraint(
            "status <> 'published' OR published_at IS NOT NULL",
            name="post_targets_published_at_present",
        ),
    )

    post = db.relationship("Post", back_populates="targets")
    account = db.relationship("SocialAccount", back_populates="targets")
    job = db.relationship(
        "PublishJob", back_populates="target", uselist=False, lazy=True
    )

    def __repr__(self):
        """Return a debug representation."""
        return f"<PostTarget {self.id} status={self.status}>"


class PublishJob(db.Model):
    """Durable publish job with a bounded lease and retry budget."""

    __tablename__ = "publish_jobs"

    id = db.Column(db.String(36), primary_key=True, default=new_id)
    target_id = db.Column(
        db.String(36),
        db.ForeignKey("post_targets.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    status = db.Column(
        _enum(JobStatus, "job_status"),
        nullable=False,
        default=JobStatus.PENDING,
    )
    due_at = db.Column(db.DateTime(timezone=True), nullable=False)
    attempts = db.Column(db.Integer, nullable=False, default=0)
    max_attempts = db.Column(db.Integer, nullable=False, default=5)
    lease_owner = db.Column(db.String(255), nullable=True)
    lease_expires_at = db.Column(db.DateTime(timezone=True), nullable=True)
    last_error_code = db.Column(db.String(127), nullable=True)
    last_error_message = db.Column(db.Text, nullable=True)
    completed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    __table_args__ = (
        db.Index("publish_jobs_due_idx", "status", "due_at"),
        db.Index(
            "publish_jobs_lease_expiry_idx",
            "lease_expires_at",
            sqlite_where=db.text("status = 'leased'"),
        ),
        db.CheckConstraint(
            "attempts BETWEEN 0 AND max_attempts",
            name="publish_jobs_attempts_bounded",
        ),
        db.CheckConstraint(
            "max_attempts > 0", name="publish_jobs_max_attempts_positive"
        ),
        db.CheckConstraint(
            "(status = 'leased' AND lease_owner IS NOT NULL "
            "AND lease_expires_at IS NOT NULL) "
            "OR (status <> 'leased' AND lease_owner IS NULL "
            "AND lease_expires_at IS NULL)",
            name="publish_jobs_lease_consistent",
        ),
        db.CheckConstraint(
            "(status IN ('succeeded', 'failed', 'uncertain', 'canceled')) "
            "= (completed_at IS NOT NULL)",
            name="publish_jobs_completed_at_consistent",
        ),
        db.CheckConstraint(
            "lease_expires_at IS NULL OR lease_expires_at > due_at",
            name="publish_jobs_due_before_lease",
        ),
    )

    target = db.relationship("PostTarget", back_populates="job")
    attempts_log = db.relationship(
        "PublishAttempt",
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="PublishAttempt.attempt_number",
        lazy=True,
    )

    def __repr__(self):
        """Return a debug representation."""
        return f"<PublishJob {self.id} status={self.status}>"


class PublishAttempt(db.Model):
    """Immutable record of one attempt against one adapter mode."""

    __tablename__ = "publish_attempts"

    id = db.Column(db.String(36), primary_key=True, default=new_id)
    job_id = db.Column(
        db.String(36),
        db.ForeignKey("publish_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    attempt_number = db.Column(db.Integer, nullable=False)
    mode = db.Column(_enum(PublishingMode, "publishing_mode"), nullable=False)
    status = db.Column(
        _enum(AttemptStatus, "attempt_status"),
        nullable=False,
        default=AttemptStatus.RUNNING,
    )
    simulated = db.Column(db.Boolean, nullable=False, default=False)
    external_post_id = db.Column(db.String(255), nullable=True)
    external_url = db.Column(db.Text, nullable=True)
    error_code = db.Column(db.String(127), nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    diagnostics = db.Column(db.JSON, nullable=True)
    started_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    finished_at = db.Column(db.DateTime(timezone=True), nullable=True)

    __table_args__ = (
        db.UniqueConstraint(
            "job_id", "attempt_number", name="publish_attempts_job_attempt_unique"
        ),
        db.Index("publish_attempts_job_started_idx", "job_id", "started_at"),
        db.CheckConstraint(
            "attempt_number > 0", name="publish_attempts_number_positive"
        ),
        db.CheckConstraint(
            "(status = 'running') = (finished_at IS NULL)",
            name="publish_attempts_finished_consistent",
        ),
        db.CheckConstraint(
            "external_url IS NULL OR external_post_id IS NOT NULL",
            name="publish_attempts_external_url_requires_id",
        ),
    )

    job = db.relationship("PublishJob", back_populates="attempts_log")

    def __repr__(self):
        """Return a debug representation."""
        return (
            f"<PublishAttempt job={self.job_id} "
            f"number={self.attempt_number} status={self.status}>"
        )


class AnalyticsSnapshot(db.Model):
    """One metric observation with explicit provenance."""

    __tablename__ = "analytics_snapshots"

    id = db.Column(db.String(36), primary_key=True, default=new_id)
    account_id = db.Column(
        db.String(36),
        db.ForeignKey("social_accounts.id", ondelete="CASCADE"),
        nullable=True,
    )
    target_id = db.Column(
        db.String(36),
        db.ForeignKey("post_targets.id", ondelete="CASCADE"),
        nullable=True,
    )
    metric = db.Column(db.String(127), nullable=False)
    value = db.Column(db.BigInteger, nullable=False)
    source = db.Column(_enum(AnalyticsSource, "analytics_source"), nullable=False)
    simulated = db.Column(db.Boolean, nullable=False)
    observed_at = db.Column(db.DateTime(timezone=True), nullable=False)
    period_start = db.Column(db.DateTime(timezone=True), nullable=True)
    period_end = db.Column(db.DateTime(timezone=True), nullable=True)
    meta = db.Column("metadata", db.JSON, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    __table_args__ = (
        db.Index(
            "analytics_snapshots_observation_unique",
            db.text("coalesce(account_id, '')"),
            db.text("coalesce(target_id, '')"),
            "metric",
            "source",
            "observed_at",
            unique=True,
        ),
        db.Index(
            "analytics_snapshots_account_observed_idx", "account_id", "observed_at"
        ),
        db.Index("analytics_snapshots_target_observed_idx", "target_id", "observed_at"),
        db.CheckConstraint(
            "account_id IS NOT NULL OR target_id IS NOT NULL",
            name="analytics_snapshots_subject_present",
        ),
        db.CheckConstraint("value >= 0", name="analytics_snapshots_value_non_negative"),
        db.CheckConstraint(
            "length(trim(metric)) > 0",
            name="analytics_snapshots_metric_not_blank",
        ),
        db.CheckConstraint(
            "(source = 'mock') = simulated",
            name="analytics_snapshots_simulated_matches_source",
        ),
        db.CheckConstraint(
            "period_start IS NULL OR period_end IS NULL OR period_end >= period_start",
            name="analytics_snapshots_period_order",
        ),
    )

    account = db.relationship("SocialAccount", lazy=True)
    target = db.relationship("PostTarget", lazy=True)

    def __repr__(self):
        """Return a debug representation."""
        return f"<AnalyticsSnapshot {self.metric}={self.value}>"
