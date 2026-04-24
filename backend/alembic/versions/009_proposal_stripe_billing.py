"""Proposal Stripe billing wiring.

Adds fields to the proposals table that track the Stripe artifacts
spawned when a client e-signs a proposal. Which artifact gets created
depends on the linked Quote's payment_type:

- one_time quotes  -> Stripe Invoice (hosted pay URL emailed by Stripe)
- subscription quotes -> Stripe Checkout Session (mode=subscription)

Either way, the Stripe object id and a shareable URL land on the
proposal row so the CRM UI and the webhook can reconcile later
without a round-trip to Stripe just to look up the link.

Revision ID: 009_proposal_stripe_billing
Revises: 008_null_empty_email_thread_ids
Create Date: 2026-04-24
"""

import sqlalchemy as sa

from alembic import op

revision = "009_proposal_stripe_billing"
down_revision = "008_null_empty_email_thread_ids"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Structured pricing on proposals. Before this, pricing lived in
    # pricing_section free text, which made it impossible to wire a
    # proposal to Stripe without a linked quote. These fields give the
    # proposal its own billable amount + cadence.
    op.add_column(
        "proposals",
        sa.Column("payment_type", sa.String(20), nullable=False, server_default="one_time"),
    )
    op.add_column(
        "proposals",
        sa.Column("recurring_interval", sa.String(20), nullable=True),
    )
    op.add_column(
        "proposals",
        sa.Column("recurring_interval_count", sa.Integer(), nullable=True),
    )
    op.add_column(
        "proposals",
        sa.Column("amount", sa.Numeric(12, 2), nullable=True),
    )
    op.add_column(
        "proposals",
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
    )

    # Quote: add recurring_interval_count so we can express bi-yearly and
    # other multiples (Stripe models this as interval=month, count=6).
    op.add_column(
        "quotes",
        sa.Column("recurring_interval_count", sa.Integer(), nullable=True),
    )

    op.add_column(
        "proposals",
        sa.Column("stripe_invoice_id", sa.String(255), nullable=True),
    )
    op.add_column(
        "proposals",
        sa.Column("stripe_subscription_id", sa.String(255), nullable=True),
    )
    op.add_column(
        "proposals",
        sa.Column("stripe_checkout_session_id", sa.String(255), nullable=True),
    )
    op.add_column(
        "proposals",
        sa.Column("stripe_payment_url", sa.Text(), nullable=True),
    )
    op.add_column(
        "proposals",
        sa.Column("invoice_sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "proposals",
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Webhooks look up proposals by invoice_id and subscription_id to flip
    # status on payment events, so index both. Session id is indexed for
    # the checkout.session.completed handler which hits it on every event.
    op.create_index(
        "ix_proposals_stripe_invoice_id", "proposals", ["stripe_invoice_id"],
    )
    op.create_index(
        "ix_proposals_stripe_subscription_id",
        "proposals",
        ["stripe_subscription_id"],
    )
    op.create_index(
        "ix_proposals_stripe_checkout_session_id",
        "proposals",
        ["stripe_checkout_session_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_proposals_stripe_checkout_session_id", table_name="proposals")
    op.drop_index("ix_proposals_stripe_subscription_id", table_name="proposals")
    op.drop_index("ix_proposals_stripe_invoice_id", table_name="proposals")
    op.drop_column("proposals", "paid_at")
    op.drop_column("proposals", "invoice_sent_at")
    op.drop_column("proposals", "stripe_payment_url")
    op.drop_column("proposals", "stripe_checkout_session_id")
    op.drop_column("proposals", "stripe_subscription_id")
    op.drop_column("proposals", "stripe_invoice_id")
    op.drop_column("quotes", "recurring_interval_count")
    op.drop_column("proposals", "currency")
    op.drop_column("proposals", "amount")
    op.drop_column("proposals", "recurring_interval_count")
    op.drop_column("proposals", "recurring_interval")
    op.drop_column("proposals", "payment_type")
