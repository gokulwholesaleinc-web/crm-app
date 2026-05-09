"""merge orphan 022_activity_contact_id_backfill into the trunk head

Revision ID: 030_merge_022_orphan
Revises: 022_activity_contact_id_backfill, 029_merge_028
Create Date: 2026-05-09

PR #215 landed ``022_activity_contact_id_backfill`` as a sibling of
``022_contracts_esign`` (both point to ``021_proposal_attachment_views``).
The trunk continued via ``022_contracts_esign`` → 023…→ ``029_merge_028``
and never picked up the backfill branch, so on next boot alembic errors
with "Multiple head revisions are present for given argument 'head'" and
the backend crashloops. No-op merge migration — the backfill UPDATE in
022_activity_contact_id_backfill still runs the first time alembic walks
that branch.
"""

from alembic import op  # noqa: F401

revision = "030_merge_022_orphan"
down_revision = ("022_activity_contact_id_backfill", "029_merge_028")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
