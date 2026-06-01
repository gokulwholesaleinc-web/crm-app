"""Add onboarding packet tables (Client Onboarding Phase 2).

Revision ID: 050_onboarding_packets
Revises: 049_onboarding
Create Date: 2026-05-31

Three tables: ``onboarding_packets`` (token-gated per-recipient bundle),
``onboarding_packet_documents`` (frozen per-template copy + field values),
and ``onboarding_packet_document_views`` (read-before-sign ledger, cloned
from ``proposal_signing_document_views``). ``proposal_onboarding_selections``
(§4.7) is deferred to Phase 3.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "050_onboarding_packets"
down_revision = "049_onboarding"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "onboarding_packets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("contact_id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=True),
        sa.Column("proposal_id", sa.Integer(), nullable=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("download_token_hash", sa.String(length=64), nullable=True),
        sa.Column(
            "download_token_expires_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="active",
            nullable=False,
        ),
        sa.Column("completing_since", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recipient_email", sa.String(length=255), nullable=False),
        sa.Column("recipient_name", sa.String(length=255), nullable=True),
        sa.Column("signer_signature_image", sa.LargeBinary(), nullable=True),
        sa.Column(
            "signature_version", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column("signer_ip", sa.String(length=45), nullable=True),
        sa.Column("signer_user_agent", sa.Text(), nullable=True),
        sa.Column("signer_timezone", sa.String(length=100), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by_id", sa.Integer(), nullable=True),
        sa.Column("abandoned_at", sa.DateTime(timezone=True), nullable=True),
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
            ["contact_id"],
            ["contacts.id"],
            name="fk_onboarding_packets_contact_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_onboarding_packets_company_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["proposal_id"],
            ["proposals.id"],
            name="fk_onboarding_packets_proposal_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["revoked_by_id"],
            ["users.id"],
            name="fk_onboarding_packets_revoked_by_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name="fk_onboarding_packets_created_by_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_id"],
            ["users.id"],
            name="fk_onboarding_packets_updated_by_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_onboarding_packets_token_hash"),
        sa.UniqueConstraint(
            "download_token_hash", name="uq_onboarding_packets_download_token_hash"
        ),
    )
    op.create_index(
        "ix_onboarding_packets_contact_id", "onboarding_packets", ["contact_id"]
    )
    op.create_index(
        "ix_onboarding_packets_status", "onboarding_packets", ["status"]
    )

    op.create_table(
        "onboarding_packet_documents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("packet_id", sa.Integer(), nullable=False),
        sa.Column(
            "display_order", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column("source_template_id", sa.Integer(), nullable=True),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("pdf_path", sa.Text(), nullable=False),
        sa.Column(
            "field_definitions",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "field_values",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "field_values_version", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column(
            "requires_esign", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
        sa.Column("esign_disclosure_snapshot", sa.Text(), nullable=True),
        sa.Column("esign_disclosure_version", sa.String(length=50), nullable=True),
        sa.Column("consented_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stamp_lease_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attachment_id", sa.Integer(), nullable=True),
        sa.Column("filled_pdf_error", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
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
            ["packet_id"],
            ["onboarding_packets.id"],
            name="fk_onboarding_packet_documents_packet_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_template_id"],
            ["onboarding_templates.id"],
            name="fk_onboarding_packet_documents_source_template_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["attachment_id"],
            ["attachments.id"],
            name="fk_onboarding_packet_documents_attachment_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name="fk_onboarding_packet_documents_created_by_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_id"],
            ["users.id"],
            name="fk_onboarding_packet_documents_updated_by_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_onboarding_packet_documents_packet_order",
        "onboarding_packet_documents",
        ["packet_id", "display_order", "id"],
    )

    op.create_table(
        "onboarding_packet_document_views",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("packet_document_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "viewed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["packet_document_id"],
            ["onboarding_packet_documents.id"],
            name="fk_onboarding_packet_document_views_doc_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "packet_document_id",
            "token_hash",
            name="uq_onboarding_packet_doc_views_doc_token",
        ),
    )
    op.create_index(
        "ix_onboarding_packet_doc_views_token_hash",
        "onboarding_packet_document_views",
        ["token_hash"],
    )
    op.create_index(
        "ix_onboarding_packet_doc_views_document",
        "onboarding_packet_document_views",
        ["packet_document_id"],
    )


def downgrade() -> None:
    # Drop in reverse FK order: views → documents → packets.
    op.drop_index(
        "ix_onboarding_packet_doc_views_document",
        table_name="onboarding_packet_document_views",
    )
    op.drop_index(
        "ix_onboarding_packet_doc_views_token_hash",
        table_name="onboarding_packet_document_views",
    )
    op.drop_table("onboarding_packet_document_views")

    op.drop_index(
        "ix_onboarding_packet_documents_packet_order",
        table_name="onboarding_packet_documents",
    )
    op.drop_table("onboarding_packet_documents")

    op.drop_index(
        "ix_onboarding_packets_status", table_name="onboarding_packets"
    )
    op.drop_index(
        "ix_onboarding_packets_contact_id", table_name="onboarding_packets"
    )
    op.drop_table("onboarding_packets")
