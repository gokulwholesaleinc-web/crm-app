"""Backfill activities.contact_id from linked opportunities.

Migration 020 added ``activities.contact_id`` so the contact's Activities
tab can mirror opportunity-driven activity. Pre-existing rows that
predate the dual-write code in ``ActivityService`` ship with a NULL
contact_id even when the parent opportunity has one — those rows would
stay invisible on the contact tab forever without a one-shot backfill.

Idempotent: ``contact_id IS NULL`` filter means re-running is a no-op.

Revision ID: 022_activity_contact_id_backfill
Revises: 021_proposal_attachment_views
Create Date: 2026-05-06
"""

from alembic import op

revision = "022_activity_contact_id_backfill"
down_revision = "021_proposal_attachment_views"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE activities
        SET contact_id = opportunities.contact_id
        FROM opportunities
        WHERE activities.entity_type = 'opportunities'
          AND activities.entity_id = opportunities.id
          AND activities.contact_id IS NULL
          AND opportunities.contact_id IS NOT NULL
        """
    )


def downgrade() -> None:
    # Backfills aren't reversible without losing data. The schema rollback
    # in 020's downgrade drops the column entirely, which makes a
    # column-level rollback here moot.
    pass
