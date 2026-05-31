"""Add onboarding_templates (Client Onboarding Phase 1).

Revision ID: 049_onboarding
Revises: 048_proposal_acceptance_evidence
Create Date: 2026-05-29
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "049_onboarding"
down_revision = "048_proposal_acceptance_evidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "onboarding_templates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("service_tag", sa.String(length=100), nullable=True),
        sa.Column("owner_id", sa.Integer(), nullable=True),
        # AuditableMixin columns (not redeclared on the model, but the DDL
        # still has to ship them).
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("updated_by_id", sa.Integer(), nullable=True),
        sa.Column("pdf_path", sa.Text(), nullable=True),
        sa.Column("pdf_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "field_definitions",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "requires_esign", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
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
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_onboarding_templates_owner_id", "onboarding_templates", ["owner_id"]
    )
    op.create_index(
        "ix_onboarding_templates_service_tag", "onboarding_templates", ["service_tag"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_onboarding_templates_service_tag", table_name="onboarding_templates"
    )
    op.drop_index(
        "ix_onboarding_templates_owner_id", table_name="onboarding_templates"
    )
    op.drop_table("onboarding_templates")
