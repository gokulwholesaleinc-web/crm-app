"""Add e-sign columns to contracts.

Revision ID: 022_contracts_esign
Revises: 021_proposal_attachment_views
Create Date: 2026-05-07

Expands `contracts` to support the e-sign workflow that mirrors proposals:
a contract can be sent for signature, viewed at a tokenized public URL,
signed (typed name + signature image + IP/UA captured), and the signed
PDF stored in R2.

File attachments reuse the existing polymorphic `attachments` table with
`entity_type='contracts'`, so no new attachments table is created here.
"""

from alembic import op

revision = "022_contracts_esign"
down_revision = "021_proposal_attachment_views"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE contracts
            ADD COLUMN IF NOT EXISTS sent_at TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS sign_token VARCHAR(64),
            ADD COLUMN IF NOT EXISTS sign_token_expires_at TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS signed_at TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS signed_by_name VARCHAR(255),
            ADD COLUMN IF NOT EXISTS signed_signature_b64 TEXT,
            ADD COLUMN IF NOT EXISTS signed_ip VARCHAR(45),
            ADD COLUMN IF NOT EXISTS signed_ua TEXT,
            ADD COLUMN IF NOT EXISTS signed_pdf_r2_key VARCHAR(255),
            ADD COLUMN IF NOT EXISTS expiring_notified_at TIMESTAMPTZ
    """)
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_contracts_sign_token "
        "ON contracts (sign_token) WHERE sign_token IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_contracts_sign_token")
    op.execute("""
        ALTER TABLE contracts
            DROP COLUMN IF EXISTS expiring_notified_at,
            DROP COLUMN IF EXISTS signed_pdf_r2_key,
            DROP COLUMN IF EXISTS signed_ua,
            DROP COLUMN IF EXISTS signed_ip,
            DROP COLUMN IF EXISTS signed_signature_b64,
            DROP COLUMN IF EXISTS signed_by_name,
            DROP COLUMN IF EXISTS signed_at,
            DROP COLUMN IF EXISTS sign_token_expires_at,
            DROP COLUMN IF EXISTS sign_token,
            DROP COLUMN IF EXISTS sent_at
    """)
