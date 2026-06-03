"""Onboarding v3 — polymorphic document model (typed-doc foundation).

Revision ID: 052_onboarding_typed_docs
Revises: 051_onboarding_selections
Create Date: 2026-06-03

The keystone migration for the v3 plugin document model (esign becomes ONE of
three kinds). Purely additive + a single NULLABLE relaxation — no data
migration (the ``DEFAULT 'esign_pdf'`` backfills the handful of existing
template rows; there are zero live packets). The 6 seed forms land in a later
idempotent seed step, NOT here.

  * ``onboarding_templates.kind`` + CHECK — relabels every existing template
    into the e-sign kind (clean cutover, no live packets).
  * ``onboarding_packet_documents.kind`` + CHECK — frozen from the template at
    create time.
  * ``onboarding_packet_documents.pdf_path`` → NULLABLE — the keystone for
    questionnaire/upload docs (no template PDF copy).
  * ``onboarding_packet_uploads`` — the fill-time upload fence (one row per
    client-uploaded file, landing each as its own contacts Attachment so the
    1:1 ``attachment_id`` fence stays reserved for the single summary artifact).

The dedicated ``onboarding_secret_values`` ciphertext table is NOT here — it
ships in its own migration ``053`` with the upload/security phase (F4 passwords
COLLECT+ENCRYPT). Single linear head; revision id is 24 chars (≤32, respects
the ``alembic_version VARCHAR(32)`` cap).
"""

import sqlalchemy as sa

from alembic import op

revision = "052_onboarding_typed_docs"
down_revision = "051_onboarding_selections"
branch_labels = None
depends_on = None

_KIND_CHECK_SQL = "kind IN ('esign_pdf', 'questionnaire', 'upload_request')"


def upgrade() -> None:
    # --- kind discriminator on both tables (backfills existing rows) --------
    op.add_column(
        "onboarding_templates",
        sa.Column(
            "kind",
            sa.String(length=20),
            server_default="esign_pdf",
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_onboarding_templates_kind", "onboarding_templates", _KIND_CHECK_SQL
    )

    op.add_column(
        "onboarding_packet_documents",
        sa.Column(
            "kind",
            sa.String(length=20),
            server_default="esign_pdf",
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_onboarding_packet_documents_kind",
        "onboarding_packet_documents",
        _KIND_CHECK_SQL,
    )

    # --- the keystone: a packet document no longer requires a PDF copy ------
    op.alter_column(
        "onboarding_packet_documents",
        "pdf_path",
        existing_type=sa.Text(),
        nullable=True,
    )

    # --- fill-time upload fence --------------------------------------------
    op.create_table(
        "onboarding_packet_uploads",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("packet_document_id", sa.Integer(), nullable=False),
        # Which file_upload question this file answers.
        sa.Column("field_id", sa.String(length=64), nullable=False),
        # The landed Attachment (NULL after scrub deletes it; the row may
        # linger briefly between scrub steps).
        sa.Column("attachment_id", sa.Integer(), nullable=True),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        # gov-ID etc.; drives owner/admin read-auth + (future) retention SLA.
        sa.Column(
            "sensitive", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
        # Which access link uploaded it (forwarded-link isolation).
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["packet_document_id"],
            ["onboarding_packet_documents.id"],
            name="fk_onboarding_packet_uploads_document_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["attachment_id"],
            ["attachments.id"],
            name="fk_onboarding_packet_uploads_attachment_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_onboarding_packet_uploads_document",
        "onboarding_packet_uploads",
        ["packet_document_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_onboarding_packet_uploads_document",
        table_name="onboarding_packet_uploads",
    )
    op.drop_table("onboarding_packet_uploads")

    # Safe to re-impose NOT NULL on a clean rollback — no questionnaire/upload
    # packet rows (with NULL pdf_path) exist to violate it.
    op.alter_column(
        "onboarding_packet_documents",
        "pdf_path",
        existing_type=sa.Text(),
        nullable=False,
    )

    op.drop_constraint(
        "ck_onboarding_packet_documents_kind",
        "onboarding_packet_documents",
        type_="check",
    )
    op.drop_column("onboarding_packet_documents", "kind")

    op.drop_constraint(
        "ck_onboarding_templates_kind", "onboarding_templates", type_="check"
    )
    op.drop_column("onboarding_templates", "kind")
