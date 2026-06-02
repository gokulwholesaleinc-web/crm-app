"""Persist interactive guide progress per account user.

Revision ID: 043_guide_progress
Revises: 042_proposal_signing_documents
Create Date: 2026-05-18
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "043_guide_progress"
down_revision = "042_proposal_signing_documents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    guide_progress_type = (
        postgresql.JSONB(astext_type=sa.Text()) if is_postgres else sa.JSON()
    )
    server_default = sa.text("'{}'::jsonb") if is_postgres else sa.text("'{}'")

    op.add_column(
        "user_preferences",
        sa.Column(
            "guide_progress",
            guide_progress_type,
            nullable=False,
            server_default=server_default,
        ),
    )
    if is_postgres:
        op.alter_column("user_preferences", "guide_progress", server_default=None)


def downgrade() -> None:
    op.drop_column("user_preferences", "guide_progress")
