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
    twice in the list — "looks like an identifier but isn't one" is
    worse than not having the field). Single-tenant CRM, so no
    tenant_id in the unique key.
  - ``designated_signer_email`` VARCHAR(255), nullable. Mirrors the
    Proposal model's field of the same name (proposals/models.py
    line 114) and the send-modal default-fill pattern from #290.

Both columns are nullable so existing rows transition cleanly — no
backfill required.

Re-run safety: every DDL step is gated by ``IF NOT EXISTS`` so a
re-run after a partial failure (lock timeout, OOM, network blip) is
idempotent. Alembic 1.7+ accepts ``if_not_exists`` on ``op.add_column``
and ``op.create_index``; the partial unique index is created via raw
SQL because Alembic's helper doesn't surface the ``WHERE`` clause.
"""

import sqlalchemy as sa

from alembic import op

revision = "032_contract_fields"
down_revision = "031_contract_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "contracts",
        sa.Column("contract_number", sa.String(length=64), nullable=True),
        if_not_exists=True,
    )
    op.add_column(
        "contracts",
        sa.Column(
            "designated_signer_email",
            sa.String(length=255),
            nullable=True,
        ),
        if_not_exists=True,
    )
    op.create_index(
        "ix_contracts_contract_number",
        "contracts",
        ["contract_number"],
        unique=False,
        if_not_exists=True,
    )
    # Partial unique index on the non-NULL subset — keeps the column
    # optional while still failing fast on duplicate operator-typed
    # numbers. Raw SQL because Alembic's ``create_index`` helper
    # doesn't expose the ``WHERE`` clause.
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS "
        "ix_contracts_contract_number_unique "
        "ON contracts (contract_number) "
        "WHERE contract_number IS NOT NULL"
    )


def downgrade() -> None:
    op.execute(
        "DROP INDEX IF EXISTS ix_contracts_contract_number_unique"
    )
    op.drop_index(
        "ix_contracts_contract_number",
        table_name="contracts",
        if_exists=True,
    )
    op.drop_column("contracts", "designated_signer_email", if_exists=True)
    op.drop_column("contracts", "contract_number", if_exists=True)
