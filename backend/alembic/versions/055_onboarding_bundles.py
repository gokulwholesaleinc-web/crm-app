"""Add onboarding template bundles (saved packets) + their ordered items.

Revision ID: 055_onboarding_bundles
Revises: 054_onboarding_template_unique
Create Date: 2026-06-05

Two tables behind the "saved packet" / wizard feature:

* ``onboarding_template_bundles`` — a named (UNIQUE), optionally-described,
  active/retired ordered list staff assemble once and reuse.
* ``onboarding_template_bundle_items`` — one ``(bundle, template)`` reference at
  a ``display_order``. ``bundle_id`` CASCADEs (deleting a bundle drops its
  items — this delete does happen); ``template_id`` is a plain FK with NO
  cascade (templates are only soft-retired, so a cascade would be decorative —
  retired members are handled in-app). Two unique constraints keep the ordering
  gap-free + collision-free.

Additive + safe (new tables only); run on real Postgres as part of the deploy.
The revision id is 21 chars (≤32, respects the ``alembic_version VARCHAR(32)``
cap that bit migration 054). FK / unique names mirror migration 051's
column-based style. The ``TimestampMixin`` ``created_at`` index is intentionally
omitted to match the existing onboarding tables (migrations 050/051): create_all
builds it for the SQLite test DB, but prod has never carried it on this family.
"""

import sqlalchemy as sa

from alembic import op

revision = "055_onboarding_bundles"
down_revision = "054_onboarding_template_unique"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "onboarding_template_bundles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "is_active", sa.Boolean(), server_default=sa.true(), nullable=False
        ),
        # AuditableMixin columns (not redeclared on the model; DDL still ships them).
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("updated_by_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name="fk_onboarding_template_bundles_created_by_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_id"],
            ["users.id"],
            name="fk_onboarding_template_bundles_updated_by_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_onboarding_template_bundles_name"),
    )
    op.create_table(
        "onboarding_template_bundle_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("bundle_id", sa.Integer(), nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column(
            "display_order", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("updated_by_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        # bundle_id CASCADE: a bundle delete removes its items.
        sa.ForeignKeyConstraint(
            ["bundle_id"],
            ["onboarding_template_bundles.id"],
            name="fk_onboarding_template_bundle_items_bundle_id",
            ondelete="CASCADE",
        ),
        # template_id: NO cascade — templates are soft-retired, never deleted.
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["onboarding_templates.id"],
            name="fk_onboarding_template_bundle_items_template_id",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name="fk_onboarding_template_bundle_items_created_by_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_id"],
            ["users.id"],
            name="fk_onboarding_template_bundle_items_updated_by_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "bundle_id",
            "template_id",
            name="uq_onboarding_template_bundle_items_template",
        ),
        sa.UniqueConstraint(
            "bundle_id",
            "display_order",
            name="uq_onboarding_template_bundle_items_order",
        ),
    )
    op.create_index(
        "ix_onboarding_template_bundle_items_bundle",
        "onboarding_template_bundle_items",
        ["bundle_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_onboarding_template_bundle_items_bundle",
        table_name="onboarding_template_bundle_items",
    )
    op.drop_table("onboarding_template_bundle_items")
    op.drop_table("onboarding_template_bundles")
