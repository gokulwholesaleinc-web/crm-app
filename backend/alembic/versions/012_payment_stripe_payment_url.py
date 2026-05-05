"""Persist Stripe hosted-payment URL on Payment.

Adds `stripe_payment_url` so the CRM can re-share the customer-facing
Stripe link if the original delivery email got lost (test mode, spam
folder, wrong email on file). Mirrors the field already on Proposal.

Revision ID: 012_payment_stripe_payment_url
Revises: 011_email_daily_goal_default_1000
Create Date: 2026-05-05
"""

import sqlalchemy as sa

from alembic import op

revision = "012_payment_stripe_payment_url"
down_revision = "011_email_daily_goal_default_1000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "payments",
        sa.Column("stripe_payment_url", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("payments", "stripe_payment_url")
