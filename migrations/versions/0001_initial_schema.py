"""Initial social publishing schema.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-11-21

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial_schema"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def enum_type(name: str, *values: str) -> sa.Enum:
    """Build a stored-as-value enum with a SQLite-friendly check constraint."""
    return sa.Enum(
        *values,
        name=name,
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
    )


def upgrade() -> None:
    """Create the initial schema."""
    op.create_table(
        "users",
        sa.Column("id", sa.String(16), primary_key=True, nullable=False),
        sa.Column("username", sa.String(255), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("failed_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("id = 'owner'", name="single_owner"),
        sa.CheckConstraint("failed_attempts >= 0", name="valid_failed_attempts"),
    )

    op.create_table(
        "sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True, nullable=False),
        sa.Column("user_id", sa.String(16), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="sessions_user_id_fkey", ondelete="CASCADE"
        ),
    )
    op.create_index("sessions_expiry_idx", "sessions", ["expires_at"])

    op.create_table(
        "social_accounts",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column(
            "platform",
            enum_type(
                "social_platform",
                "instagram",
                "facebook",
                "tiktok",
                "twitter",
                "youtube",
            ),
            nullable=False,
        ),
        sa.Column("handle", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("external_account_id", sa.String(255), nullable=True),
        sa.Column(
            "mode",
            enum_type("publishing_mode", "mock", "api", "browser", "manual"),
            nullable=False,
            server_default="mock",
        ),
        sa.Column(
            "connection_status",
            enum_type(
                "connection_status",
                "unconfigured",
                "connected",
                "expired",
                "disconnected",
            ),
            nullable=False,
            server_default="unconfigured",
        ),
        sa.Column("encrypted_credentials", sa.Text(), nullable=True),
        sa.Column("credentials_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "platform", "handle", name="social_accounts_platform_handle_unique"
        ),
        sa.UniqueConstraint(
            "id", "platform", name="social_accounts_id_platform_unique"
        ),
        sa.CheckConstraint(
            "length(trim(handle)) > 0", name="social_accounts_handle_not_blank"
        ),
        sa.CheckConstraint(
            "(encrypted_credentials IS NULL) = (credentials_updated_at IS NULL)",
            name="social_accounts_credentials_pairing",
        ),
    )
    op.create_index(
        "social_accounts_external_id_idx",
        "social_accounts",
        ["platform", "external_account_id"],
        unique=True,
        sqlite_where=sa.text("external_account_id IS NOT NULL"),
    )

    op.create_table(
        "posts",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "status",
            enum_type(
                "post_status",
                "draft",
                "scheduled",
                "publishing",
                "published",
                "partial",
                "failed",
                "canceled",
                "pending_manual",
            ),
            nullable=False,
            server_default="draft",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("posts_status_idx", "posts", ["status", "updated_at"])

    op.create_table(
        "media",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("post_id", sa.String(36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("kind", enum_type("media_kind", "image", "video"), nullable=False),
        sa.Column("storage_key", sa.String(512), nullable=False, unique=True),
        sa.Column("mime_type", sa.String(127), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("alt_text", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["post_id"], ["posts.id"], name="media_post_id_fkey", ondelete="CASCADE"
        ),
        sa.UniqueConstraint("post_id", "position", name="media_post_position_unique"),
        sa.CheckConstraint("byte_size > 0", name="media_byte_size_positive"),
        sa.CheckConstraint("position >= 0", name="media_position_non_negative"),
        sa.CheckConstraint("width IS NULL OR width > 0", name="media_width_positive"),
        sa.CheckConstraint(
            "height IS NULL OR height > 0", name="media_height_positive"
        ),
        sa.CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0",
            name="media_duration_non_negative",
        ),
        sa.CheckConstraint(
            "kind <> 'video' OR duration_ms IS NOT NULL",
            name="media_video_duration",
        ),
    )

    op.create_table(
        "post_targets",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("post_id", sa.String(36), nullable=False),
        sa.Column("account_id", sa.String(36), nullable=False),
        sa.Column(
            "platform",
            enum_type(
                "social_platform",
                "instagram",
                "facebook",
                "tiktok",
                "twitter",
                "youtube",
            ),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "status",
            enum_type(
                "target_status",
                "draft",
                "scheduled",
                "publishing",
                "published",
                "pending_manual",
                "failed",
                "uncertain",
                "canceled",
            ),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("idempotency_key", sa.String(36), nullable=False, unique=True),
        sa.Column("external_post_id", sa.String(255), nullable=True),
        sa.Column("external_url", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["post_id"],
            ["posts.id"],
            name="post_targets_post_id_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["account_id", "platform"],
            ["social_accounts.id", "social_accounts.platform"],
            name="post_targets_account_platform_fk",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "post_id", "account_id", name="post_targets_post_account_unique"
        ),
        sa.CheckConstraint(
            "status NOT IN ('scheduled', 'publishing') OR scheduled_at IS NOT NULL",
            name="post_targets_schedule_required",
        ),
        sa.CheckConstraint(
            "status <> 'published' OR published_at IS NOT NULL",
            name="post_targets_published_at_present",
        ),
    )
    op.create_index("post_targets_due_idx", "post_targets", ["status", "scheduled_at"])
    op.create_index("post_targets_account_idx", "post_targets", ["account_id"])

    op.create_table(
        "publish_jobs",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("target_id", sa.String(36), nullable=False, unique=True),
        sa.Column(
            "status",
            enum_type(
                "job_status",
                "pending",
                "leased",
                "succeeded",
                "failed",
                "uncertain",
                "canceled",
                "pending_manual",
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("lease_owner", sa.String(255), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(127), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["target_id"],
            ["post_targets.id"],
            name="publish_jobs_target_id_fkey",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "attempts BETWEEN 0 AND max_attempts",
            name="publish_jobs_attempts_bounded",
        ),
        sa.CheckConstraint(
            "max_attempts > 0", name="publish_jobs_max_attempts_positive"
        ),
        sa.CheckConstraint(
            "(status = 'leased' AND lease_owner IS NOT NULL "
            "AND lease_expires_at IS NOT NULL) "
            "OR (status <> 'leased' AND lease_owner IS NULL "
            "AND lease_expires_at IS NULL)",
            name="publish_jobs_lease_consistent",
        ),
        sa.CheckConstraint(
            "(status IN ('succeeded', 'failed', 'uncertain', 'canceled')) "
            "= (completed_at IS NOT NULL)",
            name="publish_jobs_completed_at_consistent",
        ),
        sa.CheckConstraint(
            "lease_expires_at IS NULL OR lease_expires_at > due_at",
            name="publish_jobs_due_before_lease",
        ),
    )
    op.create_index("publish_jobs_due_idx", "publish_jobs", ["status", "due_at"])
    op.create_index(
        "publish_jobs_lease_expiry_idx",
        "publish_jobs",
        ["lease_expires_at"],
        sqlite_where=sa.text("status = 'leased'"),
    )

    op.create_table(
        "publish_attempts",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("job_id", sa.String(36), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column(
            "mode",
            enum_type("publishing_mode", "mock", "api", "browser", "manual"),
            nullable=False,
        ),
        sa.Column(
            "status",
            enum_type(
                "attempt_status",
                "running",
                "published",
                "pending_manual",
                "failed",
                "uncertain",
            ),
            nullable=False,
            server_default="running",
        ),
        sa.Column("simulated", sa.Boolean(), nullable=False),
        sa.Column("external_post_id", sa.String(255), nullable=True),
        sa.Column("external_url", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(127), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("diagnostics", sa.JSON(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["publish_jobs.id"],
            name="publish_attempts_job_id_fkey",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "job_id", "attempt_number", name="publish_attempts_job_attempt_unique"
        ),
        sa.CheckConstraint(
            "attempt_number > 0", name="publish_attempts_number_positive"
        ),
        sa.CheckConstraint(
            "(status = 'running') = (finished_at IS NULL)",
            name="publish_attempts_finished_consistent",
        ),
        sa.CheckConstraint(
            "external_url IS NULL OR external_post_id IS NOT NULL",
            name="publish_attempts_external_url_requires_id",
        ),
    )
    op.create_index(
        "publish_attempts_job_started_idx",
        "publish_attempts",
        ["job_id", "started_at"],
    )

    op.create_table(
        "analytics_snapshots",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("account_id", sa.String(36), nullable=True),
        sa.Column("target_id", sa.String(36), nullable=True),
        sa.Column("metric", sa.String(127), nullable=False),
        sa.Column("value", sa.BigInteger(), nullable=False),
        sa.Column(
            "source", enum_type("analytics_source", "mock", "api"), nullable=False
        ),
        sa.Column("simulated", sa.Boolean(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["social_accounts.id"],
            name="analytics_snapshots_account_id_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["target_id"],
            ["post_targets.id"],
            name="analytics_snapshots_target_id_fkey",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "account_id IS NOT NULL OR target_id IS NOT NULL",
            name="analytics_snapshots_subject_present",
        ),
        sa.CheckConstraint("value >= 0", name="analytics_snapshots_value_non_negative"),
        sa.CheckConstraint(
            "length(trim(metric)) > 0",
            name="analytics_snapshots_metric_not_blank",
        ),
        sa.CheckConstraint(
            "(source = 'mock') = simulated",
            name="analytics_snapshots_simulated_matches_source",
        ),
        sa.CheckConstraint(
            "period_start IS NULL OR period_end IS NULL OR period_end >= period_start",
            name="analytics_snapshots_period_order",
        ),
    )
    op.create_index(
        "analytics_snapshots_observation_unique",
        "analytics_snapshots",
        [
            sa.text("coalesce(account_id, '')"),
            sa.text("coalesce(target_id, '')"),
            "metric",
            "source",
            "observed_at",
        ],
        unique=True,
    )
    op.create_index(
        "analytics_snapshots_account_observed_idx",
        "analytics_snapshots",
        ["account_id", "observed_at"],
    )
    op.create_index(
        "analytics_snapshots_target_observed_idx",
        "analytics_snapshots",
        ["target_id", "observed_at"],
    )


def downgrade() -> None:
    """Drop the initial schema in dependency order."""
    op.drop_table("analytics_snapshots")
    op.drop_table("publish_attempts")
    op.drop_table("publish_jobs")
    op.drop_table("post_targets")
    op.drop_table("media")
    op.drop_table("posts")
    op.drop_table("social_accounts")
    op.drop_table("sessions")
    op.drop_table("users")
