"""Sign-to-Confirm e-signature fields on proposals + default T&C template.

Revision ID: 037_proposal_sig_stamp
Revises: 036_seed_lc_brand
Create Date: 2026-05-14

Adds the storage Lorenzo's new Sign-to-Confirm flow needs:

* ``proposals.master_contract_pdf_path`` — R2 key of the optional master
  service agreement PDF the rep can upload on the proposal. When set,
  the client's signature image gets stamped on top of it and the
  composite is stored at ``proposals.signed_pdf_path``.
* ``proposals.signature_field_coords`` — JSONB {page, x, y, width, height}
  pointing at the slot in the master PDF where the signature image
  should land. NULL falls back to auto-detect (last page, bottom-right).
* ``proposals.signed_pdf_path`` — R2 key of the stamped + audit-appended
  PDF, populated by the accept endpoint.
* ``proposals.terms_and_conditions`` — per-proposal override of the
  T&C body rendered inside the signing modal. NULL falls back to
  ``tenant_settings.default_terms_and_conditions``.
* ``proposals.signature_image`` — raw PNG bytes of the drawn signature.
  Stored inline so the audit-trail page can render it without a
  second R2 round-trip and so reconstructing a signed copy after
  R2 loss is still possible.
* ``tenant_settings.default_terms_and_conditions`` — tenant-wide T&C
  template applied when a proposal doesn't override it.

All columns are nullable; no backfill needed. Existing accepted
proposals carry their legacy typed-name signature unchanged.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "037_proposal_sig_stamp"
down_revision = "036_seed_lc_brand"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "proposals",
        sa.Column("master_contract_pdf_path", sa.Text(), nullable=True),
    )
    op.add_column(
        "proposals",
        sa.Column(
            "signature_field_coords",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "proposals",
        sa.Column("signed_pdf_path", sa.Text(), nullable=True),
    )
    op.add_column(
        "proposals",
        sa.Column("terms_and_conditions", sa.Text(), nullable=True),
    )
    op.add_column(
        "proposals",
        sa.Column("signature_image", sa.LargeBinary(), nullable=True),
    )
    op.add_column(
        "tenant_settings",
        sa.Column("default_terms_and_conditions", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tenant_settings", "default_terms_and_conditions")
    op.drop_column("proposals", "signature_image")
    op.drop_column("proposals", "terms_and_conditions")
    op.drop_column("proposals", "signed_pdf_path")
    op.drop_column("proposals", "signature_field_coords")
    op.drop_column("proposals", "master_contract_pdf_path")
