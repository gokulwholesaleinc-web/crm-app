"""Tenant email tagline + social links for the branded email wrapper.

Revision ID: 034_email_socials
Revises: 033_mailchimp_blocked
Create Date: 2026-05-13

The branded email wrapper is being redesigned to match the Link Creative
marketing template: white header with centered logo, brand tagline below
the wordmark, gold accent rule, and a black footer with a row of social
links. The header tagline and the six social URLs are tenant-configurable
so other tenants (if onboarded) still render their own copy and links.

`tagline` is plain text (max 255 chars). URLs are validated http(s) at the
Pydantic layer; column type matches the existing 500-char URL columns.
Defaults are empty (NULL) — the email wrapper omits the entire section
when no values are present, so legacy tenants render the prior layout
without a footer-socials block.
"""

from alembic import op

revision = "034_email_socials"
down_revision = "033_mailchimp_blocked"
branch_labels = None
depends_on = None


_COLS = (
    "tagline VARCHAR(255)",
    "social_facebook_url VARCHAR(500)",
    "social_instagram_url VARCHAR(500)",
    "social_tiktok_url VARCHAR(500)",
    "social_linkedin_url VARCHAR(500)",
    "social_youtube_url VARCHAR(500)",
    "social_website_url VARCHAR(500)",
)


def upgrade() -> None:
    # No backfill — NULL is the documented "no value" sentinel that the
    # email wrapper checks via _safe_url() before rendering anything.
    for col in _COLS:
        op.execute(f"ALTER TABLE tenant_settings ADD COLUMN IF NOT EXISTS {col}")


def downgrade() -> None:
    for col in reversed(_COLS):
        name = col.split()[0]
        op.execute(f"ALTER TABLE tenant_settings DROP COLUMN IF EXISTS {name}")
