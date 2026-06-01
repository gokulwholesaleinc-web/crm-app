"""Add proposal→onboarding-template selection join table (Phase 3, §4.7).

Revision ID: 051_onboarding_selections
Revises: 050_onboarding_packets
Create Date: 2026-06-01

``proposal_onboarding_selections`` is the staff-curated, ordered set of
onboarding templates that the Phase-3 auto-send trigger turns into a packet
when a proposal is accepted. One row per (proposal, template); ``display_order``
is the packet document order. Both ``proposal_id`` and ``template_id`` FKs
CASCADE on delete (a soft-retire via ``is_active`` keeps the row — the trigger
skips inactive templates at fire time; only a hard template delete drops it).
The ``(proposal_id, display_order)`` unique constraint enforces a gap-free,
collision-free ordering (the reorder service bumps to a temp offset first).
"""

import sqlalchemy as sa

from alembic import op

revision = "051_onboarding_selections"
down_revision = "050_onboarding_packets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "proposal_onboarding_selections",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("proposal_id", sa.Integer(), nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column(
            "display_order", sa.Integer(), server_default="0", nullable=False
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
            ["proposal_id"],
            ["proposals.id"],
            name="fk_proposal_onboarding_selections_proposal_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["onboarding_templates.id"],
            name="fk_proposal_onboarding_selections_template_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name="fk_proposal_onboarding_selections_created_by_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_id"],
            ["users.id"],
            name="fk_proposal_onboarding_selections_updated_by_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "proposal_id", "template_id", name="uq_proposal_onboarding_selection"
        ),
        sa.UniqueConstraint(
            "proposal_id",
            "display_order",
            name="uq_proposal_onboarding_selection_order",
        ),
    )
    op.create_index(
        "ix_proposal_onboarding_selections_proposal",
        "proposal_onboarding_selections",
        ["proposal_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_proposal_onboarding_selections_proposal",
        table_name="proposal_onboarding_selections",
    )
    op.drop_table("proposal_onboarding_selections")
