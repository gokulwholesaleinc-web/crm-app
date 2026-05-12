"""Contract: contract_number + designated_signer_email.

Revision ID: 032_contract_fields
Revises: 031_contract_audit
Create Date: 2026-05-11

Two new optional fields surfaced to operators (Giancarlo asked for a
human-readable contract reference on the list + detail header), and
needed by the send/resend modal flow shipped in #290 so the recipient
defaults to the contract's designated signer instead of falling back
to the linked contact's primary email every send.

  - ``contract_number`` VARCHAR(64), nullable. Operator-facing
    reference like "CO-2026-0001". Gets BOTH a non-unique B-tree
    index (so list-page filters/sorts on the column don't scan) AND
    a *partial unique* index on the non-NULL subset (so duplicate
    numbers fail loudly with a 23505 instead of silently appearing
    twice in the list).
  - ``designated_signer_email`` VARCHAR(255), nullable. Mirrors the
    Proposal model's field of the same name and the send-modal
    default-fill pattern from #290.

Both columns are nullable so existing rows transition cleanly — no
backfill required.

Re-run safety: every DDL step goes through raw SQL with PostgreSQL's
native ``IF NOT EXISTS`` / ``IF EXISTS`` clauses. The prior revision
relied on ``op.add_column(if_not_exists=True)``/``op.create_index(
if_not_exists=True)`` which need Alembic 1.14+; prod is pinned to
1.13.1, which fails-fast with ``TypeError: add_column() got an
unexpected keyword argument 'if_not_exists'`` and wedges the entire
deploy.
"""

from alembic import op

revision = "032_contract_fields"
down_revision = "031_contract_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE contracts "
        "ADD COLUMN IF NOT EXISTS contract_number VARCHAR(64)"
    )
    op.execute(
        "ALTER TABLE contracts "
        "ADD COLUMN IF NOT EXISTS designated_signer_email VARCHAR(255)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_contracts_contract_number "
        "ON contracts (contract_number)"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS "
        "ix_contracts_contract_number_unique "
        "ON contracts (contract_number) "
        "WHERE contract_number IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_contracts_contract_number_unique")
    op.execute("DROP INDEX IF EXISTS ix_contracts_contract_number")
    op.execute(
        "ALTER TABLE contracts DROP COLUMN IF EXISTS designated_signer_email"
    )
    op.execute(
        "ALTER TABLE contracts DROP COLUMN IF EXISTS contract_number"
    )
