"""Add contact_id to activities for opportunity-linked activity cross-reference.

When an Activity is created against an opportunity, we want to know which
contact it implicitly relates to so the contact's Activities tab shows
opportunity-driven activity without each caller having to create two rows.

Revision ID: 020_activity_contact_id
Revises: 019_gmail_send_as_aliases
Create Date: 2026-05-06
"""

from alembic import op

revision = "020_activity_contact_id"
down_revision = "019_gmail_send_as_aliases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE activities "
        "ADD COLUMN IF NOT EXISTS contact_id INTEGER "
        "REFERENCES contacts(id) ON DELETE SET NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_activities_contact_id "
        "ON activities (contact_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_activities_contact_id")
    op.execute("ALTER TABLE activities DROP COLUMN IF EXISTS contact_id")
