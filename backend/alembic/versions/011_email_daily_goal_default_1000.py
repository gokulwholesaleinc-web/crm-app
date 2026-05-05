"""Bump email_settings default daily send goal 200 → 1000.

Giancarlo at Link Creative needs to send ~1000/day for cold-outreach
campaigns; the previous 200 was a conservative initial cap that was
also being shown in the UI as "daily limit". Reframed as a daily
goal (still soft-capped at this value to protect sender reputation).

Updates rows that still hold the prior default (200) so existing
tenants pick up the new ceiling. Tenants who already customized
their value (anything other than 200) are left alone.

Revision ID: 011_email_daily_goal_default_1000
Revises: 010_proposal_billing_error
Create Date: 2026-05-05
"""

from alembic import op

revision = "011_email_daily_goal_default_1000"
down_revision = "010_proposal_billing_error"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "UPDATE email_settings SET daily_send_limit = 1000 WHERE daily_send_limit = 200"
    )
    op.execute(
        "UPDATE email_settings SET warmup_target_daily = 1000 WHERE warmup_target_daily = 200"
    )
    op.execute(
        "ALTER TABLE email_settings ALTER COLUMN daily_send_limit SET DEFAULT 1000"
    )
    op.execute(
        "ALTER TABLE email_settings ALTER COLUMN warmup_target_daily SET DEFAULT 1000"
    )


def downgrade() -> None:
    # Reverse the row updates too — leaving rows at 1000 with a DEFAULT
    # of 200 would put the table in a permanently inconsistent state.
    # Symmetric with upgrade(): only flips rows that still hold the
    # post-upgrade value.
    op.execute(
        "UPDATE email_settings SET daily_send_limit = 200 WHERE daily_send_limit = 1000"
    )
    op.execute(
        "UPDATE email_settings SET warmup_target_daily = 200 WHERE warmup_target_daily = 1000"
    )
    op.execute(
        "ALTER TABLE email_settings ALTER COLUMN daily_send_limit SET DEFAULT 200"
    )
    op.execute(
        "ALTER TABLE email_settings ALTER COLUMN warmup_target_daily SET DEFAULT 200"
    )
