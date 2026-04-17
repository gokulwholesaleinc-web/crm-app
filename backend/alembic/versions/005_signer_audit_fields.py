"""Add signer audit fields to proposals and quotes.

Proposals gain the full e-signature column set that Quotes already has
(signer_name, signer_email, signer_ip, signed_at, rejection_reason).

Both tables gain:
- signer_user_agent — captured alongside signer_ip on accept for forensic audit
- designated_signer_email — optional override. When set, the public /accept
  endpoint rejects submissions whose signer_email doesn't match (case-
  insensitive). When NULL, the legacy behavior holds: signer_email must
  match the linked contact's email.

Also merges the 004_lead_nullable_names + 004_user_approval heads.

Revision ID: 005_signer_audit
Revises: 004_lead_nullable_names, 004_user_approval
Create Date: 2026-04-15
"""

import sqlalchemy as sa

from alembic import op

revision = "005_signer_audit"
down_revision = ("004_lead_nullable_names", "004_user_approval")
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Proposal: full signer column set (mirror of Quote)
    op.add_column("proposals", sa.Column("signer_name", sa.String(255), nullable=True))
    op.add_column("proposals", sa.Column("signer_email", sa.String(255), nullable=True))
    op.add_column("proposals", sa.Column("signer_ip", sa.String(45), nullable=True))
    op.add_column("proposals", sa.Column("signer_user_agent", sa.Text(), nullable=True))
    op.add_column("proposals", sa.Column("signed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("proposals", sa.Column("rejection_reason", sa.Text(), nullable=True))
    op.add_column("proposals", sa.Column("designated_signer_email", sa.String(255), nullable=True))

    # Quote: fill in the two columns missing for full audit parity
    op.add_column("quotes", sa.Column("signer_user_agent", sa.Text(), nullable=True))
    op.add_column("quotes", sa.Column("designated_signer_email", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("quotes", "designated_signer_email")
    op.drop_column("quotes", "signer_user_agent")

    op.drop_column("proposals", "designated_signer_email")
    op.drop_column("proposals", "rejection_reason")
    op.drop_column("proposals", "signed_at")
    op.drop_column("proposals", "signer_user_agent")
    op.drop_column("proposals", "signer_ip")
    op.drop_column("proposals", "signer_email")
    op.drop_column("proposals", "signer_name")
