"""Proposal signing date placement and public document views.

Revision ID: 045_proposal_date_fields_doc_views
Revises: 044_admin_audit_work_sessions
Create Date: 2026-05-20
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "045_proposal_date_fields_doc_views"
down_revision = "044_admin_audit_work_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "proposals",
        sa.Column(
            "date_field_coords",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "proposals",
        sa.Column("signer_timezone", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "proposal_signing_documents",
        sa.Column(
            "date_field_coords",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.create_table(
        "proposal_signing_document_views",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "document_id",
            sa.Integer(),
            sa.ForeignKey("proposal_signing_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "viewed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.UniqueConstraint(
            "document_id",
            "token_hash",
            name="uq_proposal_signing_document_views_doc_token",
        ),
    )
    op.create_index(
        "ix_proposal_signing_document_views_token_hash",
        "proposal_signing_document_views",
        ["token_hash"],
    )
    op.create_index(
        "ix_proposal_signing_document_views_document",
        "proposal_signing_document_views",
        ["document_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_proposal_signing_document_views_document",
        table_name="proposal_signing_document_views",
    )
    op.drop_index(
        "ix_proposal_signing_document_views_token_hash",
        table_name="proposal_signing_document_views",
    )
    op.drop_table("proposal_signing_document_views")
    op.drop_column("proposal_signing_documents", "date_field_coords")
    op.drop_column("proposals", "signer_timezone")
    op.drop_column("proposals", "date_field_coords")
