"""Prune far-future calendar sync rows for user 93.

Google Calendar singleEvents expansion on 7 never-ending recurring meetings
generated ~4000 activity rows stretching to 2056. With the 90-day timeMax
cap now in place, these rows will never be re-created.

Deletes calendar_sync_events + activities where:
- user_id = 93
- entity_type = 'users' (Google-synced meetings are linked to the owning user)
- activity_type = 'meeting'
- due_date > now() + interval '90 days'

Revision ID: 006_prune_far_future
Revises: 005_signer_audit
Create Date: 2026-04-15
"""

from alembic import op


revision = "006_prune_far_future"
down_revision = "005_signer_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        DELETE FROM calendar_sync_events
        WHERE activity_id IN (
            SELECT id FROM activities
            WHERE owner_id = 93
              AND entity_type = 'users'
              AND activity_type = 'meeting'
              AND due_date > now() + interval '90 days'
        )
    """)
    op.execute("""
        DELETE FROM activities
        WHERE owner_id = 93
          AND entity_type = 'users'
          AND activity_type = 'meeting'
          AND due_date > now() + interval '90 days'
    """)


def downgrade() -> None:
    pass
