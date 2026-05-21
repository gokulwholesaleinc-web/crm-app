"""Proposal packages and selected package snapshot.

Revision ID: 046_proposal_packages
Revises: 045_proposal_date_placement
Create Date: 2026-05-20
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "046_proposal_packages"
down_revision = "045_proposal_date_placement"
branch_labels = None
depends_on = None


def _json_type():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        return postgresql.JSONB(astext_type=sa.Text())
    return sa.JSON()


def upgrade() -> None:
    op.create_table(
        "proposal_packages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "proposal_id",
            sa.Integer(),
            sa.ForeignKey("proposals.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="USD"),
        sa.Column("payment_type", sa.String(length=20), nullable=False, server_default="one_time"),
        sa.Column("recurring_interval", sa.String(length=20), nullable=True),
        sa.Column("recurring_interval_count", sa.Integer(), nullable=True),
        sa.Column("subtotal", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("discount_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("tax_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("total", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_recommended", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.CheckConstraint("subtotal >= 0", name="ck_proposal_packages_subtotal_nonnegative"),
        sa.CheckConstraint("discount_amount >= 0", name="ck_proposal_packages_discount_nonnegative"),
        sa.CheckConstraint("tax_amount >= 0", name="ck_proposal_packages_tax_nonnegative"),
        sa.CheckConstraint("total >= 0", name="ck_proposal_packages_total_nonnegative"),
        sa.CheckConstraint(
            "payment_type in ('one_time', 'subscription')",
            name="ck_proposal_packages_payment_type",
        ),
        sa.CheckConstraint(
            "currency = upper(currency) AND length(currency) = 3",
            name="ck_proposal_packages_currency_upper",
        ),
        sa.CheckConstraint(
            "(payment_type = 'subscription' AND recurring_interval in ('month', 'year') "
            "AND recurring_interval_count >= 1) OR "
            "(payment_type = 'one_time' AND recurring_interval IS NULL "
            "AND recurring_interval_count IS NULL)",
            name="ck_proposal_packages_cadence",
        ),
    )
    op.create_index(
        "ix_proposal_packages_proposal_order",
        "proposal_packages",
        ["proposal_id", "sort_order", "id"],
    )
    op.create_index(
        "uq_proposal_packages_one_recommended",
        "proposal_packages",
        ["proposal_id"],
        unique=True,
        # Only ACTIVE recommended packages compete for the slot; a
        # deactivated recommended row must not block creating a new one.
        postgresql_where=sa.text("is_recommended = true AND is_active = true"),
        sqlite_where=sa.text("is_recommended = 1 AND is_active = 1"),
    )

    op.create_table(
        "proposal_package_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "package_id",
            sa.Integer(),
            sa.ForeignKey("proposal_packages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            sa.Integer(),
            sa.ForeignKey("products.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "price_id",
            sa.Integer(),
            sa.ForeignKey("prices.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("quantity", sa.Numeric(10, 2), nullable=False),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("discount_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("total", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.CheckConstraint("quantity > 0", name="ck_proposal_package_items_quantity_positive"),
        sa.CheckConstraint("unit_price >= 0", name="ck_proposal_package_items_price_nonnegative"),
        sa.CheckConstraint(
            "discount_amount >= 0",
            name="ck_proposal_package_items_discount_nonnegative",
        ),
        sa.CheckConstraint("total >= 0", name="ck_proposal_package_items_total_nonnegative"),
    )
    op.create_index(
        "ix_proposal_package_items_package_order",
        "proposal_package_items",
        ["package_id", "sort_order", "id"],
    )
    op.create_index(
        "ix_proposal_package_items_product_id",
        "proposal_package_items",
        ["product_id"],
    )
    op.create_index(
        "ix_proposal_package_items_price_id",
        "proposal_package_items",
        ["price_id"],
    )

    op.add_column("proposals", sa.Column("selected_package_id", sa.Integer(), nullable=True))
    op.add_column("proposals", sa.Column("selected_package_snapshot", _json_type(), nullable=True))
    op.create_foreign_key(
        "fk_proposals_selected_package_id",
        "proposals",
        "proposal_packages",
        ["selected_package_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_proposals_selected_package_id",
        "proposals",
        ["selected_package_id"],
    )
    # Selection-vs-snapshot symmetry: both columns set or both NULL. Guards
    # against the orphan-snapshot case where a hard-delete of a package row
    # (via admin SQL or future code) nulls the FK via ON DELETE SET NULL
    # but leaves the snapshot pointing at a non-existent package_id, and
    # against the inverse where a snapshot was persisted without the FK.
    op.create_check_constraint(
        "ck_proposals_selected_package_pair",
        "proposals",
        "(selected_package_id IS NULL) = (selected_package_snapshot IS NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_proposals_selected_package_pair", "proposals", type_="check")
    op.drop_index("ix_proposals_selected_package_id", table_name="proposals")
    op.drop_constraint("fk_proposals_selected_package_id", "proposals", type_="foreignkey")
    op.drop_column("proposals", "selected_package_snapshot")
    op.drop_column("proposals", "selected_package_id")
    op.drop_index("ix_proposal_package_items_price_id", table_name="proposal_package_items")
    op.drop_index("ix_proposal_package_items_product_id", table_name="proposal_package_items")
    op.drop_index("ix_proposal_package_items_package_order", table_name="proposal_package_items")
    op.drop_table("proposal_package_items")
    op.drop_index("uq_proposal_packages_one_recommended", table_name="proposal_packages")
    op.drop_index("ix_proposal_packages_proposal_order", table_name="proposal_packages")
    op.drop_table("proposal_packages")
