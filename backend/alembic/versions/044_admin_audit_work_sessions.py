"""Add work sessions for admin audit dashboard.

Revision ID: 044_admin_audit_work_sessions
Revises: 043_guide_progress
Create Date: 2026-05-18
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "044_admin_audit_work_sessions"
down_revision = "043_guide_progress"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    metadata_type = (
        postgresql.JSONB(astext_type=sa.Text())
        if bind.dialect.name == "postgresql"
        else sa.JSON()
    )

    op.create_table(
        "work_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), server_default="0", nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("metadata", metadata_type, nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_work_sessions_user_id", "work_sessions", ["user_id"])
    op.create_index("ix_work_sessions_started_at", "work_sessions", ["started_at"])
    op.create_index("ix_work_sessions_last_seen_at", "work_sessions", ["last_seen_at"])
    op.create_index("ix_work_sessions_user_seen", "work_sessions", ["user_id", "last_seen_at"])
    op.create_index("ix_work_sessions_entity", "work_sessions", ["entity_type", "entity_id"])
    op.create_index(
        "ix_work_sessions_open",
        "work_sessions",
        ["user_id", "entity_type", "entity_id", "ended_at"],
    )
    # Partial unique index on the OPEN session per (user, entity, source).
    # Without it, two heartbeats firing in the same tick (the 45s interval
    # + a visibilitychange) can both SELECT zero open rows and both INSERT,
    # leaving two open sessions that extend independently and silently
    # double Time-by-Rep. SQLite supports partial indexes via raw SQL.
    if bind.dialect.name in ("postgresql", "sqlite"):
        op.execute(
            "CREATE UNIQUE INDEX uq_work_sessions_open_per_entity "
            "ON work_sessions (user_id, entity_type, entity_id, source) "
            "WHERE ended_at IS NULL"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name in ("postgresql", "sqlite"):
        op.execute("DROP INDEX IF EXISTS uq_work_sessions_open_per_entity")
    op.drop_index("ix_work_sessions_open", table_name="work_sessions")
    op.drop_index("ix_work_sessions_entity", table_name="work_sessions")
    op.drop_index("ix_work_sessions_user_seen", table_name="work_sessions")
    op.drop_index("ix_work_sessions_last_seen_at", table_name="work_sessions")
    op.drop_index("ix_work_sessions_started_at", table_name="work_sessions")
    op.drop_index("ix_work_sessions_user_id", table_name="work_sessions")
    op.drop_table("work_sessions")
