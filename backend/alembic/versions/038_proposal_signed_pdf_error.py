"""Operator-visible failure capture for proposal signed-PDF stamping.

Revision ID: 038_proposal_signed_pdf_error
Revises: 037_proposal_sig_stamp
Create Date: 2026-05-14

Adds ``proposals.signed_pdf_error`` so the accept endpoint's fail-soft
stamp path can leave a breadcrumb the CRM UI surfaces as a re-stamp
banner. Without this column, a corrupt master PDF or transient R2 blip
produces a silently-accepted proposal with no countersigned copy and
no signal to the operator.

Nullable, no backfill.
"""

import sqlalchemy as sa
from alembic import op

revision = "038_proposal_signed_pdf_error"
down_revision = "037_proposal_sig_stamp"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "proposals",
        sa.Column("signed_pdf_error", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("proposals", "signed_pdf_error")
