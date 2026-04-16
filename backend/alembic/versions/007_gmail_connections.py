"""Gmail email-log integration: per-user Gmail OAuth connections, sync state cursors, and email_queue/inbound_emails extensions for RFC 5322 Message-Id + thread dedup.

Also merges the 004_lead_nullable_names and 004_user_approval branches so alembic has a single head going forward.

Revision ID: 007_gmail_connections
Revises: 006_prune_far_future
Create Date: 2026-04-15
"""

from alembic import op
import sqlalchemy as sa


revision = "007_gmail_connections"
down_revision = "006_prune_far_future"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "gmail_connections",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("access_token", sa.Text(), nullable=False),
        sa.Column("refresh_token", sa.Text(), nullable=True),
        sa.Column("token_expiry", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scopes", sa.Text(), nullable=False),
        sa.Column("history_id", sa.String(64), nullable=True),
        sa.Column("watch_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_gmail_connections_user_id",
        "gmail_connections",
        ["user_id"],
    )
    op.create_index(
        "ix_gmail_connections_email",
        "gmail_connections",
        ["email"],
    )

    op.create_table(
        "gmail_sync_state",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("last_history_id", sa.String(64), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "failure_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )

    op.add_column(
        "email_queue",
        sa.Column("message_id", sa.String(500), nullable=True),
    )
    op.add_column(
        "email_queue",
        sa.Column("thread_id", sa.String(255), nullable=True),
    )
    op.add_column(
        "email_queue",
        sa.Column(
            "sent_via",
            sa.String(20),
            nullable=False,
            server_default="resend",
        ),
    )
    op.create_index(
        "ix_email_queue_message_id",
        "email_queue",
        ["message_id"],
        unique=True,
        postgresql_where=sa.text("message_id IS NOT NULL"),
    )
    op.create_index(
        "ix_email_queue_thread_id",
        "email_queue",
        ["thread_id"],
    )

    op.create_index(
        "ix_inbound_emails_message_id",
        "inbound_emails",
        ["message_id"],
        unique=True,
        postgresql_where=sa.text("message_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_inbound_emails_message_id", table_name="inbound_emails")
    op.drop_index("ix_email_queue_thread_id", table_name="email_queue")
    op.drop_index("ix_email_queue_message_id", table_name="email_queue")
    op.drop_column("email_queue", "sent_via")
    op.drop_column("email_queue", "thread_id")
    op.drop_column("email_queue", "message_id")
    op.drop_table("gmail_sync_state")
    op.drop_index("ix_gmail_connections_email", table_name="gmail_connections")
    op.drop_index("ix_gmail_connections_user_id", table_name="gmail_connections")
    op.drop_table("gmail_connections")
