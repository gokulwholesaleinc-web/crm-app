"""merge two 028 heads (contract_cd + notify_optin) into single head

Revision ID: 029_merge_028
Revises: 028_contract_cd, 028_notify_optin
Create Date: 2026-05-08

PR #272 (contract channel-aware cooldown) and PR #275 (notification opt-in
defaults) both branched off 027 in parallel and produced two 028 heads.
Alembic on Railway boot then errors with "Multiple head revisions are
present for given argument 'head'" and the backend never starts. This
empty merge migration joins them into a single head; no schema work.
"""

from alembic import op  # noqa: F401

revision = "029_merge_028"
down_revision = ("028_contract_cd", "028_notify_optin")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
