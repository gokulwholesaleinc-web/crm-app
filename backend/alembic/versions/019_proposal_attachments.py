"""Per-token view ledger for proposal attachments (read-before-sign gate).

Revision ID: 019_proposal_attachments
Revises: 018_email_participants
Create Date: 2026-05-06
"""

from alembic import op

revision = "019_proposal_attachments"
down_revision = "018_email_participants"
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
