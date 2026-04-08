"""Add Google OAuth identity columns to users.

Adds google_sub + auth_provider and makes hashed_password nullable so
OAuth-only accounts can be created via Google sign-in.

Revision ID: 002_google_oauth
Revises: 001_stripe_invoice
Create Date: 2026-04-08
"""

from alembic import op
import sqlalchemy as sa


revision = "002_google_oauth"
down_revision = "001_stripe_invoice"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("google_sub", sa.String(255), nullable=True),
    )
    op.create_index(
        "ix_users_google_sub",
        "users",
        ["google_sub"],
        unique=True,
        postgresql_where=sa.text("google_sub IS NOT NULL"),
    )
    op.add_column(
        "users",
        sa.Column(
            "auth_provider",
            sa.String(20),
            nullable=False,
            server_default="password",
        ),
    )
    op.alter_column(
        "users",
        "hashed_password",
        existing_type=sa.String(255),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "users",
        "hashed_password",
        existing_type=sa.String(255),
        nullable=False,
    )
    op.drop_column("users", "auth_provider")
    op.drop_index("ix_users_google_sub", table_name="users")
    op.drop_column("users", "google_sub")
