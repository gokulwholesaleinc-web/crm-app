"""Backfill EntityShare rows so existing contracts remain visible to all active users.

Revision ID: 026_contracts_share_backfill
Revises: 025_campaigns_share_backfill
Create Date: 2026-05-07

Before this migration, contracts had no privacy plumbing — every authenticated
user could see every contract. Now that the list + detail endpoints honour
data_scope, this migration pre-populates EntityShare so the rollout is
non-breaking: every contract is shared with every currently-active user
(except its owner).

Idempotent: ON CONFLICT DO NOTHING + the unique index makes re-running safe.

Downgrade is intentionally NOT implemented — distinguishing backfill rows
from user-created shares post-hoc is impossible without a backfill flag,
and a blanket DELETE would destroy real user shares.
"""

from alembic import op

revision = "026_contracts_share_backfill"
down_revision = "025_campaigns_share_backfill"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO entity_shares (
            entity_type, entity_id, shared_with_user_id, shared_by_user_id,
            permission_level, created_at, updated_at
        )
        SELECT
            'contracts',
            c.id,
            u.id,
            c.owner_id,
            'view',
            NOW(),
            NOW()
        FROM contracts c
        CROSS JOIN users u
        WHERE u.id != c.owner_id
          AND u.is_active = TRUE
        ON CONFLICT (entity_type, entity_id, shared_with_user_id) DO NOTHING
    """)


def downgrade() -> None:
    raise NotImplementedError(
        "026_contracts_share_backfill is one-way: a blanket DELETE would also "
        "remove real user-created shares. To revert, restore from backup."
    )
