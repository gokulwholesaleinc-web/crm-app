"""Add Campaign.send_via and Campaign.mailchimp_campaign_id.

Revision ID: 017_campaign_send_via_mailchimp
Revises: 016_mailchimp_connection
Create Date: 2026-05-05
"""

from alembic import op

revision = "017_campaign_send_via_mailchimp"
down_revision = "016_mailchimp_connection"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE campaigns "
        "ADD COLUMN IF NOT EXISTS send_via VARCHAR(20) NOT NULL DEFAULT 'resend'"
    )
    op.execute(
        "ALTER TABLE campaigns "
        "ADD COLUMN IF NOT EXISTS mailchimp_campaign_id VARCHAR(64)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE campaigns DROP COLUMN IF EXISTS mailchimp_campaign_id")
    op.execute("ALTER TABLE campaigns DROP COLUMN IF EXISTS send_via")
