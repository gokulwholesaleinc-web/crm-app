"""Replace proposal packages with proposal bundles.

Revision ID: 047_proposal_bundles
Revises: 046_proposal_packages
Create Date: 2026-05-21
"""

import sqlalchemy as sa

from alembic import op

revision = "047_proposal_bundles"
down_revision = "046_proposal_packages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "proposal_bundles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("bundle_number", sa.String(length=50), nullable=False),
        sa.Column("public_token", sa.String(length=64), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("selected_proposal_id", sa.Integer(), nullable=True),
        sa.Column("selected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("viewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "contact_id",
            sa.Integer(),
            sa.ForeignKey("contacts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "owner_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_proposal_bundles_bundle_number", "proposal_bundles", ["bundle_number"], unique=True)
    op.create_index("ix_proposal_bundles_public_token", "proposal_bundles", ["public_token"], unique=True)
    op.create_index("ix_proposal_bundles_selected_proposal_id", "proposal_bundles", ["selected_proposal_id"])
    op.create_index("ix_proposal_bundles_contact_id", "proposal_bundles", ["contact_id"])
    op.create_index("ix_proposal_bundles_company_id", "proposal_bundles", ["company_id"])
    op.create_index("ix_proposal_bundles_owner_id", "proposal_bundles", ["owner_id"])

    op.add_column("proposals", sa.Column("proposal_bundle_id", sa.Integer(), nullable=True))
    op.add_column(
        "proposals",
        sa.Column("bundle_sort_order", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "proposals",
        sa.Column("bundle_is_recommended", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_foreign_key(
        "fk_proposals_proposal_bundle_id",
        "proposals",
        "proposal_bundles",
        ["proposal_bundle_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_proposal_bundles_selected_proposal_id",
        "proposal_bundles",
        "proposals",
        ["selected_proposal_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_proposals_bundle_order",
        "proposals",
        ["proposal_bundle_id", "bundle_sort_order", "id"],
    )
    op.create_index(
        "uq_proposals_one_recommended_per_bundle",
        "proposals",
        ["proposal_bundle_id"],
        unique=True,
        postgresql_where=sa.text("bundle_is_recommended = true AND proposal_bundle_id IS NOT NULL"),
        sqlite_where=sa.text("bundle_is_recommended = 1 AND proposal_bundle_id IS NOT NULL"),
    )

    # PR #378's package schema was deployed as an intermediate shape. The
    # product model is now real proposal options grouped under a bundle, so the
    # package artifacts are intentionally removed. Any accepted selected-package
    # snapshot data is lost on this upgrade; there are no Stripe side effects in
    # the retired package MVP.
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


def downgrade() -> None:
    # Recreate the retired package schema so a downgrade can run. Bundle fields
    # that never existed in packages are not recoverable.
    op.create_table(
        "proposal_packages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("proposal_id", sa.Integer(), sa.ForeignKey("proposals.id", ondelete="CASCADE"), nullable=False),
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
    )
    op.create_index("ix_proposal_packages_proposal_order", "proposal_packages", ["proposal_id", "sort_order", "id"])
    op.create_index(
        "uq_proposal_packages_one_recommended",
        "proposal_packages",
        ["proposal_id"],
        unique=True,
        postgresql_where=sa.text("is_recommended = true AND is_active = true"),
        sqlite_where=sa.text("is_recommended = 1 AND is_active = 1"),
    )
    op.create_table(
        "proposal_package_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("package_id", sa.Integer(), sa.ForeignKey("proposal_packages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="SET NULL"), nullable=True),
        sa.Column("price_id", sa.Integer(), sa.ForeignKey("prices.id", ondelete="SET NULL"), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("quantity", sa.Numeric(10, 2), nullable=False),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("discount_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("total", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_proposal_package_items_package_order", "proposal_package_items", ["package_id", "sort_order", "id"])
    op.create_index("ix_proposal_package_items_product_id", "proposal_package_items", ["product_id"])
    op.create_index("ix_proposal_package_items_price_id", "proposal_package_items", ["price_id"])
    op.add_column("proposals", sa.Column("selected_package_id", sa.Integer(), nullable=True))
    op.add_column("proposals", sa.Column("selected_package_snapshot", sa.JSON(), nullable=True))
    op.create_foreign_key(
        "fk_proposals_selected_package_id",
        "proposals",
        "proposal_packages",
        ["selected_package_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_proposals_selected_package_id", "proposals", ["selected_package_id"])
    op.create_check_constraint(
        "ck_proposals_selected_package_pair",
        "proposals",
        "(selected_package_id IS NULL) = (selected_package_snapshot IS NULL)",
    )

    op.drop_index("uq_proposals_one_recommended_per_bundle", table_name="proposals")
    op.drop_index("ix_proposals_bundle_order", table_name="proposals")
    op.drop_constraint("fk_proposal_bundles_selected_proposal_id", "proposal_bundles", type_="foreignkey")
    op.drop_constraint("fk_proposals_proposal_bundle_id", "proposals", type_="foreignkey")
    op.drop_column("proposals", "bundle_is_recommended")
    op.drop_column("proposals", "bundle_sort_order")
    op.drop_column("proposals", "proposal_bundle_id")
    op.drop_index("ix_proposal_bundles_owner_id", table_name="proposal_bundles")
    op.drop_index("ix_proposal_bundles_company_id", table_name="proposal_bundles")
    op.drop_index("ix_proposal_bundles_contact_id", table_name="proposal_bundles")
    op.drop_index("ix_proposal_bundles_selected_proposal_id", table_name="proposal_bundles")
    op.drop_index("ix_proposal_bundles_public_token", table_name="proposal_bundles")
    op.drop_index("ix_proposal_bundles_bundle_number", table_name="proposal_bundles")
    op.drop_table("proposal_bundles")
