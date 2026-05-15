"""Seed Link Creative dark-mode (white-text) logo URL.

Revision ID: 040_seed_lc_dark_logo
Revises: 039_tenant_logo_url_dark
Create Date: 2026-05-15

Migration 039 added ``tenant_settings.logo_url_dark``; this migration
fills in Link Creative's published white-text wordmark so dark mode
swaps to it without an admin walking through Settings → Branding.

Same empty-cell guard as ``036_seed_lc_brand``: only fills if the
admin hasn't already set a value. Downgrade reverts only the cells
still carrying the seeded URL.

The URL is the agency's own WordPress upload, served from their
production domain — same source the email-template tagline +
socials were seeded from in migration 036.
"""

from alembic import op

revision = "040_seed_lc_dark_logo"
down_revision = "039_tenant_logo_url_dark"
branch_labels = None
depends_on = None


_LOGO_URL_DARK = "https://linkcreativeco.com/wp-content/uploads/2025/12/lc-logo-white-768x100.png"


def upgrade() -> None:
    op.execute(
        f"""
        UPDATE tenant_settings
        SET logo_url_dark = '{_LOGO_URL_DARK}'
        WHERE logo_url_dark IS NULL OR logo_url_dark = ''
        """
    )


def downgrade() -> None:
    op.execute(
        f"""
        UPDATE tenant_settings
        SET logo_url_dark = NULL
        WHERE logo_url_dark = '{_LOGO_URL_DARK}'
        """
    )
