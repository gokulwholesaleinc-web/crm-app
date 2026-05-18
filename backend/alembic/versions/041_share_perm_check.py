"""Constrain entity share permission levels.

Revision ID: 041_share_perm_check
Revises: 040_seed_lc_dark_logo
Create Date: 2026-05-18
"""

from alembic import op

revision = "041_share_perm_check"
down_revision = "040_seed_lc_dark_logo"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE entity_shares
        SET permission_level = 'view'
        WHERE permission_level NOT IN ('view', 'edit', 'assignee')
        """
    )
    op.create_check_constraint(
        "ck_entity_shares_permission_level",
        "entity_shares",
        "permission_level IN ('view', 'edit', 'assignee')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_entity_shares_permission_level",
        "entity_shares",
        type_="check",
    )
