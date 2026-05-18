"""Per-channel cooldown for contract_expiring notifications.

Revision ID: 028_contract_cd
Revises: 027_branding_bg
Create Date: 2026-05-08

Today the contract-lifecycle scheduler stamps a single
``expiring_notified_at`` AFTER firing the in-app notification but
BEFORE checking the email gate. If a user has email turned off for
``contract_expiring``, the in-app side still consumes the 30-day
cooldown — and when they later enable email, they're locked out of
email notifications for up to 30 days.

This migration adds a sibling column so each channel tracks its own
cooldown stamp. The scheduler's selection query ORs both columns so a
contract re-enters the candidate set if either channel is overdue,
and each branch stamps independently after a successful fire.

Defaults to NULL so existing contracts re-trigger email at the next
daily scan if the owner's email pref is enabled.

Revision id is 14 chars, comfortably under VARCHAR(32).
"""

import sqlalchemy as sa

from alembic import op

revision = "028_contract_cd"
down_revision = "027_branding_bg"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "contracts",
        sa.Column(
            "expiring_email_notified_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("contracts", "expiring_email_notified_at")
