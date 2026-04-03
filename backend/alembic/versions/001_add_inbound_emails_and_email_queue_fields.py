"""Add inbound_emails table and from_email/cc/bcc to email_queue.

Revision ID: 001_inbound_emails
Revises: None
Create Date: 2026-04-03
"""
from alembic import op
import sqlalchemy as sa

revision = "001_inbound_emails"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add new columns to email_queue
    op.add_column("email_queue", sa.Column("from_email", sa.String(255), nullable=True))
    op.add_column("email_queue", sa.Column("cc", sa.Text(), nullable=True))
    op.add_column("email_queue", sa.Column("bcc", sa.Text(), nullable=True))

    # Create inbound_emails table
    op.create_table(
        "inbound_emails",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("resend_email_id", sa.String(255), unique=True, nullable=False),
        sa.Column("from_email", sa.String(255), nullable=False),
        sa.Column("to_email", sa.String(255), nullable=False),
        sa.Column("cc", sa.Text(), nullable=True),
        sa.Column("bcc", sa.Text(), nullable=True),
        sa.Column("subject", sa.String(500), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=True),
        sa.Column("body_html", sa.Text(), nullable=True),
        sa.Column("message_id", sa.String(500), nullable=True),
        sa.Column("in_reply_to", sa.String(500), nullable=True),
        sa.Column("attachments", sa.JSON(), nullable=True),
        sa.Column("entity_type", sa.String(50), nullable=True),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_inbound_emails_entity", "inbound_emails", ["entity_type", "entity_id"])
    op.create_index("ix_inbound_emails_from", "inbound_emails", ["from_email"])

    # Create email_settings table
    op.create_table(
        "email_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("daily_send_limit", sa.Integer(), nullable=False, server_default="200"),
        sa.Column("warmup_enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("warmup_start_date", sa.Date(), nullable=True),
        sa.Column("warmup_target_daily", sa.Integer(), nullable=False, server_default="200"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("email_settings")
    op.drop_index("ix_inbound_emails_from", table_name="inbound_emails")
    op.drop_index("ix_inbound_emails_entity", table_name="inbound_emails")
    op.drop_table("inbound_emails")
    op.drop_column("email_queue", "bcc")
    op.drop_column("email_queue", "cc")
    op.drop_column("email_queue", "from_email")
