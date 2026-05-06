"""Per-token view ledger for proposal attachments (read-before-sign gate).

Revision ID: 021_proposal_attachment_views
Revises: 020_activity_contact_id
Create Date: 2026-05-06

Originally written as 019_proposal_attachments alongside PR #208 but the
file was lost during a branch reconciliation — main shipped 020_activity
on top of 019_gmail_send_as_aliases without the proposal-attachments
table. Re-applied here as 021 with the correct down_revision so prod
gets the table.
"""

from alembic import op

revision = "021_proposal_attachment_views"
down_revision = "020_activity_contact_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS proposal_attachment_views (
            id SERIAL PRIMARY KEY,
            attachment_id INTEGER NOT NULL REFERENCES attachments(id) ON DELETE CASCADE,
            token_hash VARCHAR(64) NOT NULL,
            viewed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            ip_address VARCHAR(45),
            user_agent TEXT,
            UNIQUE (attachment_id, token_hash)
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_proposal_attachment_views_token_hash "
        "ON proposal_attachment_views (token_hash)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_proposal_attachment_views_attachment "
        "ON proposal_attachment_views (attachment_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_proposal_attachment_views_attachment")
    op.execute("DROP INDEX IF EXISTS ix_proposal_attachment_views_token_hash")
    op.execute("DROP TABLE IF EXISTS proposal_attachment_views")
