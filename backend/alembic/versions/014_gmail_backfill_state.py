"""Add gmail_backfill_state table for historical email backfill tracking.

Stores per-user progress (status, counts, timestamps, error) for the
background job that backfills pre-connect Gmail messages into CRM.

Revision ID: 014_gmail_backfill_state
Revises: 013_payment_checkout_unique
Create Date: 2026-05-05
"""

from alembic import op
import sqlalchemy as sa

revision = "014_gmail_backfill_state"
down_revision = "013_payment_checkout_unique"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS gmail_backfill_state (
            user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            processed_count INTEGER NOT NULL DEFAULT 0,
            total_count INTEGER NOT NULL DEFAULT 0,
            started_at TIMESTAMPTZ,
            finished_at TIMESTAMPTZ,
            error TEXT
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS gmail_backfill_state")
