"""User approval gate: is_approved column + rejected_access_emails table.

New Google OAuth sign-ins create a pending (is_approved=False) account.
Admins approve or reject via /api/admin/users/pending.
Rejected emails are hard-blocked from re-registering.

Revision ID: 004_user_approval
Revises: 003_audit_s2
Create Date: 2026-04-15
"""

import sqlalchemy as sa

from alembic import op

revision = "004_user_approval"
down_revision = "003_audit_s2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "is_approved",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
    )

    op.create_table(
        "rejected_access_emails",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column(
            "rejected_by_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "rejected_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_rejected_access_emails_email",
        "rejected_access_emails",
        ["email"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_rejected_access_emails_email", table_name="rejected_access_emails")
    op.drop_table("rejected_access_emails")
    op.drop_column("users", "is_approved")
