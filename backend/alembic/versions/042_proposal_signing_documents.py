"""Multiple signing documents per proposal.

Revision ID: 042_proposal_signing_documents
Revises: 041_share_perm_check
Create Date: 2026-05-18
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "042_proposal_signing_documents"
down_revision = "041_share_perm_check"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "proposal_signing_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "proposal_id",
            sa.Integer(),
            sa.ForeignKey("proposals.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column(
            "content_type",
            sa.String(length=100),
            nullable=False,
            server_default="application/pdf",
        ),
        sa.Column("pdf_path", sa.Text(), nullable=False),
        sa.Column(
            "signature_field_coords",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("signed_pdf_path", sa.Text(), nullable=True),
        sa.Column("signed_pdf_error", sa.Text(), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_by_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "updated_by_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
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
    )
    op.create_index(
        "ix_proposal_signing_documents_proposal_id",
        "proposal_signing_documents",
        ["proposal_id"],
    )
    op.create_index(
        "ix_proposal_signing_documents_proposal_order",
        "proposal_signing_documents",
        ["proposal_id", "display_order", "id"],
    )
    op.execute(
        """
        INSERT INTO proposal_signing_documents (
            proposal_id,
            original_filename,
            file_size,
            content_type,
            pdf_path,
            signature_field_coords,
            signed_pdf_path,
            signed_pdf_error,
            display_order,
            created_by_id,
            updated_by_id,
            created_at,
            updated_at
        )
        SELECT
            p.id,
            'Master service agreement.pdf',
            0,
            'application/pdf',
            p.master_contract_pdf_path,
            p.signature_field_coords,
            p.signed_pdf_path,
            p.signed_pdf_error,
            0,
            p.created_by_id,
            p.updated_by_id,
            COALESCE(p.created_at, NOW()),
            COALESCE(p.updated_at, NOW())
        FROM proposals p
        WHERE p.master_contract_pdf_path IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM proposal_signing_documents d
              WHERE d.proposal_id = p.id
          )
        """
    )


def downgrade() -> None:
    op.drop_index(
        "ix_proposal_signing_documents_proposal_order",
        table_name="proposal_signing_documents",
    )
    op.drop_index(
        "ix_proposal_signing_documents_proposal_id",
        table_name="proposal_signing_documents",
    )
    op.drop_table("proposal_signing_documents")
