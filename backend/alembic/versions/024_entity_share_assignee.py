"""Widen entity_shares.permission_level for the multi-assignee value.

Revision ID: 024_entity_share_assignee
Revises: 023_account_settings
Create Date: 2026-05-07

The column was VARCHAR(10) holding "view" or "edit". The multi-assignee
sharing feature introduces "assignee" (8 chars — fits) and reserves
headroom for future levels by widening to VARCHAR(20). No data change.
"""

from alembic import op

revision = "024_entity_share_assignee"
down_revision = "023_account_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE entity_shares "
        "ALTER COLUMN permission_level TYPE VARCHAR(20)"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE entity_shares SET permission_level = 'view' "
        "WHERE permission_level NOT IN ('view', 'edit')"
    )
    op.execute(
        "ALTER TABLE entity_shares "
        "ALTER COLUMN permission_level TYPE VARCHAR(10)"
    )
