"""Unique partial index on payments.stripe_checkout_session_id.

Mirrors the existing partial unique index on stripe_invoice_id. With
the now-stable subscription idempotency key, a network retry after
Stripe.Session.create succeeds but before db.flush() commits would
otherwise be able to insert a second Payment row pointing at the same
session — and the webhook processor would only update one. The unique
index makes the second insert raise IntegrityError so the dedup is
visible at the DB layer.

Partial (WHERE col IS NOT NULL) so the column can stay nullable for
non-checkout payments (e.g. plain invoices, payment intents).

Revision ID: 013_payment_checkout_session_unique
Revises: 012_payment_stripe_payment_url
Create Date: 2026-05-05
"""

from alembic import op

revision = "013_payment_checkout_session_unique"
down_revision = "012_payment_stripe_payment_url"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_payments_stripe_checkout_session_id_unique "
        "ON payments(stripe_checkout_session_id) WHERE stripe_checkout_session_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute(
        "DROP INDEX IF EXISTS ix_payments_stripe_checkout_session_id_unique"
    )
