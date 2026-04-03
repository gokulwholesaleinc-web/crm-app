"""Add stripe_invoice_id to payments table.

Revision ID: 001_stripe_invoice
Revises:
Create Date: 2026-04-03
"""

from alembic import op
import sqlalchemy as sa

revision = "001_stripe_invoice"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "payments",
        sa.Column("stripe_invoice_id", sa.String(255), nullable=True),
    )
    op.create_index(
        "ix_payments_stripe_invoice_id",
        "payments",
        ["stripe_invoice_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_payments_stripe_invoice_id", table_name="payments")
    op.drop_column("payments", "stripe_invoice_id")
