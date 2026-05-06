"""Add participant_emails arrays + GIN indexes for per-user email visibility.

Revision ID: 018_email_participants
Revises: 017_campaign_send_via_mailchimp
Create Date: 2026-05-05
"""

from alembic import op

revision = "018_email_participants"
down_revision = "017_campaign_send_via_mailchimp"
branch_labels = None
depends_on = None


_EMAIL_REGEX = r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"


def upgrade() -> None:
    op.execute(
        "ALTER TABLE inbound_emails "
        "ADD COLUMN IF NOT EXISTS participant_emails TEXT[] NOT NULL DEFAULT '{}'"
    )
    op.execute(
        "ALTER TABLE email_queue "
        "ADD COLUMN IF NOT EXISTS participant_emails TEXT[] NOT NULL DEFAULT '{}'"
    )

    # Backfill: extract every bare email from From/To/CC/BCC, lowercase, dedupe.
    # Postgres regex on the concatenated headers gets us 99% accuracy without
    # needing a Python pass — RFC 5322 display names are stripped because the
    # regex only matches addr-spec. The FILTER clause keeps the array empty
    # for rows whose headers have no parseable address (LEFT JOIN otherwise
    # leaks a {NULL} into the aggregate).
    backfill_sql = """
    UPDATE {table} SET participant_emails = sub.addrs
    FROM (
        SELECT t.id,
               COALESCE(
                   array_agg(DISTINCT lower(m.match)) FILTER (WHERE m.match IS NOT NULL),
                   ARRAY[]::TEXT[]
               ) AS addrs
        FROM {table} t
        LEFT JOIN LATERAL (
            SELECT (regexp_matches(
                concat_ws(',',
                    coalesce(t.from_email, ''),
                    coalesce(t.to_email, ''),
                    coalesce(t.cc, ''),
                    coalesce(t.bcc, '')
                ),
                '{regex}',
                'g'
            ))[1] AS match
        ) m ON true
        GROUP BY t.id
    ) sub
    WHERE {table}.id = sub.id AND {table}.participant_emails = '{{}}';
    """
    op.execute(backfill_sql.format(table="inbound_emails", regex=_EMAIL_REGEX))
    op.execute(backfill_sql.format(table="email_queue", regex=_EMAIL_REGEX))

    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_inbound_emails_participants "
        "ON inbound_emails USING GIN (participant_emails)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_email_queue_participants "
        "ON email_queue USING GIN (participant_emails)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_inbound_emails_participants")
    op.execute("DROP INDEX IF EXISTS ix_email_queue_participants")
    op.execute("ALTER TABLE inbound_emails DROP COLUMN IF EXISTS participant_emails")
    op.execute("ALTER TABLE email_queue DROP COLUMN IF EXISTS participant_emails")
