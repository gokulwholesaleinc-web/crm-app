"""Add proposal acceptance evidence fields.

Revision ID: 048_proposal_acceptance_evidence
Revises: 047_proposal_bundles
Create Date: 2026-05-27
"""

import sqlalchemy as sa
from alembic import op

revision = "048_proposal_acceptance_evidence"
down_revision = "047_proposal_bundles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "proposals",
        sa.Column("agreed_to_terms_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "proposals",
        sa.Column("terms_and_conditions_snapshot", sa.Text(), nullable=True),
    )
    op.add_column(
        "proposals",
        sa.Column("esign_disclosure_snapshot", sa.Text(), nullable=True),
    )
    op.add_column(
        "proposals",
        sa.Column("esign_disclosure_version", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "proposals",
        sa.Column("acceptance_method", sa.String(length=50), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("proposals", "acceptance_method")
    op.drop_column("proposals", "esign_disclosure_version")
    op.drop_column("proposals", "esign_disclosure_snapshot")
    op.drop_column("proposals", "terms_and_conditions_snapshot")
    op.drop_column("proposals", "agreed_to_terms_at")
