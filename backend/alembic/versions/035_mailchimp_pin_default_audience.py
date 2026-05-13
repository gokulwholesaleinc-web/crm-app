"""Pin CRM-Managed Contacts (b5afe45258) as default Mailchimp audience.

Revision ID: 035_mc_pin_audience
Revises: 034_email_socials
Create Date: 2026-05-13

The CRM is single-tenant by design and ops just created a dedicated
Mailchimp audience named "CRM-Managed Contacts" (id `b5afe45258`) to
serve as the safe default destination for any CRM send. PR #320
scoped each campaign send to a static segment of only its CRM
members, PR #322 added a UI blocklist of off-limits audiences, and
this migration finishes the Layer-2 default by pinning the new
audience as ``default_audience_id`` on the active connection.

Only updates rows where ``default_audience_id`` is NULL (or empty)
and ``revoked_at IS NULL`` so an admin who has already pinned a
different audience via the UI keeps their choice. The downgrade
reverses only rows that still match the value we wrote.
"""

from alembic import op

revision = "035_mc_pin_audience"
down_revision = "034_email_socials"
branch_labels = None
depends_on = None


_AUDIENCE_ID = "b5afe45258"
_AUDIENCE_NAME = "CRM-Managed Contacts"


def upgrade() -> None:
    # Idempotent: only fills NULL/empty defaults on currently-active
    # connections. Existing pins (admin-set via UI) are left alone.
    op.execute(
        f"""
        UPDATE mailchimp_connections
        SET default_audience_id = '{_AUDIENCE_ID}',
            default_audience_name = COALESCE(
                NULLIF(default_audience_name, ''),
                '{_AUDIENCE_NAME}'
            )
        WHERE revoked_at IS NULL
          AND (default_audience_id IS NULL OR default_audience_id = '')
        """
    )


def downgrade() -> None:
    # Only revert rows that still carry the value we wrote — an admin
    # who repointed elsewhere keeps their choice.
    op.execute(
        f"""
        UPDATE mailchimp_connections
        SET default_audience_id = NULL,
            default_audience_name = NULL
        WHERE default_audience_id = '{_AUDIENCE_ID}'
          AND default_audience_name = '{_AUDIENCE_NAME}'
        """
    )
