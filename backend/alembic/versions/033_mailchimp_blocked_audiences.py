"""Mailchimp: per-connection blocked_audience_ids.

Admins use this to mark specific Mailchimp audiences as off-limits for
CRM sends — typically a marketing team's pre-existing contact list that
the CRM should never touch. The frontend audience picker filters
blocked ids out of its dropdown.

Defense-in-depth on top of the per-send static segment scoping (PR
#320). Layer 1: each send is scoped to a segment of only campaign
members, so even an unblocked-but-large audience can't be blasted.
Layer 2: ``default_audience_id`` points at an empty CRM-managed
audience (set up by ops). Layer 3 (this migration): explicit blocklist
so the dangerous audiences can't be selected via the UI.

Revision ID: 033_mailchimp_blocked
Revises: 032_contract_fields
Create Date: 2026-05-13
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY

from alembic import op

revision = "033_mailchimp_blocked"
down_revision = "032_contract_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "mailchimp_connections",
        sa.Column(
            "blocked_audience_ids",
            ARRAY(sa.String(64)),
            nullable=False,
            server_default="{}",
        ),
    )


def downgrade() -> None:
    op.drop_column("mailchimp_connections", "blocked_audience_ids")
