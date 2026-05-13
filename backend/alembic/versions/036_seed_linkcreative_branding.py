"""Seed Link Creative tagline + social URLs on the single-tenant deployment.

Revision ID: 036_seed_lc_brand
Revises: 035_mc_pin_audience
Create Date: 2026-05-13

CRM is single-tenant by design (per project memory). Migration 034
added empty ``tagline`` + six ``social_*_url`` columns to
``tenant_settings``; this migration seeds the verified Link Creative
values so the redesigned email wrapper renders on-brand on the next
deploy without requiring an admin to walk through Settings → Branding.

Each ``UPDATE`` is COALESCE-guarded: only fills NULL/empty cells, so
an admin who has already configured a different value via the UI
keeps their choice. Downgrade reverts only the cells that still match
exactly what we wrote.
"""

from alembic import op

revision = "036_seed_lc_brand"
down_revision = "035_mc_pin_audience"
branch_labels = None
depends_on = None


_TAGLINE = "ACCESSIBLE MEDIA | AUTHENTIC STORYTELLING | REAL RESULTS"
_SOCIALS: tuple[tuple[str, str], ...] = (
    ("social_facebook_url", "https://www.facebook.com/people/Link-Creative/61563260504127/"),
    ("social_instagram_url", "https://www.instagram.com/linkcreativeco/"),
    ("social_tiktok_url", "https://www.tiktok.com/@linkcreativeco"),
    ("social_linkedin_url", "https://www.linkedin.com/company/linkcreativeco"),
    ("social_youtube_url", "https://www.youtube.com/@linkcreativeco"),
    ("social_website_url", "https://linkcreativeco.com/"),
)


def upgrade() -> None:
    # Tagline first — separate statement so a constraint error on one
    # social URL doesn't roll back the tagline (each is independent).
    op.execute(
        f"""
        UPDATE tenant_settings
        SET tagline = '{_TAGLINE}'
        WHERE tagline IS NULL OR tagline = ''
        """
    )
    for column, url in _SOCIALS:
        op.execute(
            f"""
            UPDATE tenant_settings
            SET {column} = '{url}'
            WHERE {column} IS NULL OR {column} = ''
            """
        )


def downgrade() -> None:
    # Only revert cells that still carry the value we seeded.
    op.execute(
        f"""
        UPDATE tenant_settings
        SET tagline = NULL
        WHERE tagline = '{_TAGLINE}'
        """
    )
    for column, url in _SOCIALS:
        op.execute(
            f"""
            UPDATE tenant_settings
            SET {column} = NULL
            WHERE {column} = '{url}'
            """
        )
