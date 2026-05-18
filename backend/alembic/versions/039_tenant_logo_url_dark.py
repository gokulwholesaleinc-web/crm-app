"""Dark-mode logo URL on tenant_settings.

Revision ID: 039_tenant_logo_url_dark
Revises: 038_proposal_signed_pdf_error
Create Date: 2026-05-15

Adds ``tenant_settings.logo_url_dark`` so each tenant can supply a
white-text variant of its logo for dark mode without overloading the
single ``logo_url`` field. Renderers fall back to ``logo_url`` when
the dark URL is NULL, so existing tenants continue to work unchanged.

Nullable, no backfill.
"""

import sqlalchemy as sa

from alembic import op

revision = "039_tenant_logo_url_dark"
down_revision = "038_proposal_signed_pdf_error"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenant_settings",
        sa.Column("logo_url_dark", sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tenant_settings", "logo_url_dark")
