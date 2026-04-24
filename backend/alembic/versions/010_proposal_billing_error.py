"""Proposal billing_error column.

Adds a free-text column that captures the most recent Stripe-spawn
failure (bad key, customer resolution, API error) so the CRM admin
can see *why* an accepted proposal has no payment link and either
fix the root cause + retry, or reach out to the client manually.

Without this column, `_maybe_spawn_billing` silently logged the
failure and left the proposal stuck in `accepted` with no
stripe_payment_url — invisible to the CRM user.

Revision ID: 010_proposal_billing_error
Revises: 009_proposal_stripe_billing
Create Date: 2026-04-24
"""

import sqlalchemy as sa

from alembic import op

revision = "010_proposal_billing_error"
down_revision = "009_proposal_stripe_billing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "proposals",
        sa.Column("billing_error", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("proposals", "billing_error")
