"""Backfill EntityShare rows so existing campaigns remain visible to all active users.

Revision ID: 025_campaigns_share_backfill
Revises: 024_entity_share_assignee
Create Date: 2026-05-07

The campaigns privacy lockdown restricts list and detail endpoints so that
sales_reps only see their own campaigns plus any explicitly shared ones.
This migration backfills 'view' EntityShare rows for every active non-owner
user × every existing campaign so no rep loses access on rollout.

Idempotent: ON CONFLICT DO NOTHING + the unique index makes re-running safe.

Downgrade is intentionally NOT implemented — distinguishing backfill rows
from user-created shares post-hoc is impossible without a backfill flag,
and a blanket DELETE would destroy real user shares.
"""

from alembic import op

revision = "025_campaigns_share_backfill"
down_revision = "024_entity_share_assignee"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO entity_shares (
            entity_type,
            entity_id,
            shared_with_user_id,
            shared_by_user_id,
            permission_level,
            created_at,
            updated_at
        )
        SELECT
            'campaigns',
            c.id,
            u.id,
            c.owner_id,
            'view',
            NOW(),
            NOW()
        FROM campaigns c
        CROSS JOIN users u
        WHERE u.id != c.owner_id
          AND u.is_active = TRUE
        ON CONFLICT (entity_type, entity_id, shared_with_user_id) DO NOTHING
        """
    )


def downgrade() -> None:
    raise NotImplementedError(
        "025_campaigns_share_backfill is one-way: a blanket DELETE would also "
        "remove real user-created shares. To revert, restore from backup."
    )
