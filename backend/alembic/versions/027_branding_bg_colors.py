"""Admin-configurable page + surface background colors per tenant, per theme.

Revision ID: 027_branding_bg
Revises: 026_contracts_share_backfill
Create Date: 2026-05-08

Branding has carried primary/secondary/accent since launch but page and
card backgrounds were hardcoded in Tailwind (`bg-gray-50` light,
`bg-gray-900` dark). The dark default reads as "more dark blue than
black" because gray-900 is rgb(17,24,39) — meaningfully blue-shifted.
Rather than swap the hardcoded value, expose all four to the admin
branding form so each tenant can tune their own palette.

Defaults match the previous Tailwind values exactly so existing tenants
see no visual change after the migration runs.

Chained off 026 (contracts share backfill from PR #259); revision id is
17 chars, comfortably under the alembic_version VARCHAR(32) ceiling
(see 023 history note).
"""

from alembic import op

revision = "027_branding_bg"
down_revision = "026_contracts_share_backfill"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE tenant_settings "
        "ADD COLUMN IF NOT EXISTS bg_color_light VARCHAR(7) NOT NULL DEFAULT '#f9fafb'"
    )
    op.execute(
        "ALTER TABLE tenant_settings "
        "ADD COLUMN IF NOT EXISTS bg_color_dark VARCHAR(7) NOT NULL DEFAULT '#111827'"
    )
    op.execute(
        "ALTER TABLE tenant_settings "
        "ADD COLUMN IF NOT EXISTS surface_color_light VARCHAR(7) NOT NULL DEFAULT '#ffffff'"
    )
    op.execute(
        "ALTER TABLE tenant_settings "
        "ADD COLUMN IF NOT EXISTS surface_color_dark VARCHAR(7) NOT NULL DEFAULT '#1f2937'"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE tenant_settings DROP COLUMN IF EXISTS surface_color_dark")
    op.execute("ALTER TABLE tenant_settings DROP COLUMN IF EXISTS surface_color_light")
    op.execute("ALTER TABLE tenant_settings DROP COLUMN IF EXISTS bg_color_dark")
    op.execute("ALTER TABLE tenant_settings DROP COLUMN IF EXISTS bg_color_light")
