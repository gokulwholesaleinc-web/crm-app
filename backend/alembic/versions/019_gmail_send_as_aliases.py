"""Add aliases column to gmail_connections for send-as classification.

Revision ID: 019_gmail_send_as_aliases
Revises: 018_email_participants
Create Date: 2026-05-06
"""

from alembic import op

revision = "019_gmail_send_as_aliases"
down_revision = "018_email_participants"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE gmail_connections "
        "ADD COLUMN IF NOT EXISTS aliases TEXT[] NOT NULL DEFAULT '{}'"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE gmail_connections DROP COLUMN IF EXISTS aliases")
