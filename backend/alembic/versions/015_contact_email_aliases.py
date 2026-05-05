"""Add contact_email_aliases table for per-contact alternate email addresses.

Revision ID: 015_contact_email_aliases
Revises: 014_gmail_backfill_state
Create Date: 2026-05-05
"""

from alembic import op

revision = "015_contact_email_aliases"
down_revision = "014_gmail_backfill_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS contact_email_aliases (
            id SERIAL PRIMARY KEY,
            contact_id INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            email VARCHAR(255) NOT NULL,
            label VARCHAR(100),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE UNIQUE INDEX ix_contact_email_aliases_email
        ON contact_email_aliases (LOWER(email))
    """)
    op.execute("""
        CREATE INDEX ix_contact_email_aliases_contact
        ON contact_email_aliases (contact_id)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS contact_email_aliases")
