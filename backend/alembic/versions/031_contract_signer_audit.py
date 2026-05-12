"""Contract e-sign audit parity with Proposal.

Revision ID: 031_contract_audit
Revises: 030_merge_022_orphan
Create Date: 2026-05-11

PR #290 added a ContractAuditCard that reads `signer_email`,
`signer_ip`, and `signer_user_agent` off the Contract entity. Today
the contracts router *captures* the IP + UA on the public-sign
endpoint (`signer_ip = get_client_ip(request)`, `signer_ua =
request.headers.get("user-agent")`) and the service persists them as
`signed_ip` / `signed_ua`. The signer's email is captured for
identity-check (line 305 of contracts/service.py compares it to the
contact's email) but is then thrown away — the Contract row never
records who signed.

This migration brings Contract to parity with Proposal so the audit
card has real data to display and the audit trail is durable:

  - Rename `signed_ip` → `signer_ip` (still VARCHAR(45) for IPv6).
  - Rename `signed_ua` → `signer_user_agent` (still TEXT).
  - Add `signer_email` VARCHAR(255), nullable — populated at sign
    time from the request body.

`signed_by_name` is intentionally left alone — the ContractAuditCard
already coalesces `signer_name ?? signed_by_name`, so renaming is
not required to fix the audit card and would balloon the diff.

Deploy notes:
  - Postgres ALTER COLUMN RENAME is metadata-only and the lock is
    microsecond-fast on a table this small. The rename itself isn't
    a row-rewrite hazard.
  - It is NOT strictly zero-downtime in a rolling deploy though:
    during the swap, old backend pods are still issuing
    ``SELECT … signed_ip, signed_ua …`` via SQLAlchemy. Those
    queries fail with "column does not exist" until the old pod
    drains. Practical impact on the single-instance Railway deploy
    is a short blip; flagging so a future multi-instance topology
    knows to switch to add-column + dual-write + drop instead.
  - Downgrade is LOSSY for ``signer_email``: any signature captured
    while 031 was live is dropped by the column-drop, with no
    archive table. Take a ``pg_dump`` of ``contracts.signer_email``
    before downgrading if the captured audit trail still matters.
"""

import sqlalchemy as sa

from alembic import op

revision = "031_contract_audit"
down_revision = "030_merge_022_orphan"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Postgres does not support ``RENAME COLUMN ... IF EXISTS`` on
    # ALTER TABLE — only the table-level ``ALTER TABLE IF EXISTS``
    # variant takes IF EXISTS. So a re-run after a partial failure
    # (first rename committed, second crashed) requires manual
    # unwind. The contracts table is small enough that this hasn't
    # been worth the DO-block dance — but don't pretend otherwise.
    op.execute(
        "ALTER TABLE contracts RENAME COLUMN signed_ip TO signer_ip"
    )
    op.execute(
        "ALTER TABLE contracts RENAME COLUMN signed_ua TO signer_user_agent"
    )
    op.add_column(
        "contracts",
        sa.Column("signer_email", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("contracts", "signer_email")
    op.execute(
        "ALTER TABLE contracts RENAME COLUMN signer_user_agent TO signed_ua"
    )
    op.execute(
        "ALTER TABLE contracts RENAME COLUMN signer_ip TO signed_ip"
    )
