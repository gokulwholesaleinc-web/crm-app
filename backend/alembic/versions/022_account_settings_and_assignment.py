"""Account-settings tables + assignment-rule fallback flag + assignment_log.

Revision ID: 022_account_settings_and_assignment
Revises: 021_proposal_attachment_views
Create Date: 2026-05-07

Single migration covers two adjacent feature areas:

1. Lead auto-assignment wiring — `assignment_rules.is_default` lets one
   rule serve as the catch-all when no filtered rule matches; new
   `assignment_log` table records every routing decision (rule match,
   default fallback, manual override) for audit and reporting.

2. Account Settings — `user_notification_prefs` and `user_preferences`
   back the two Settings tiles that were rendering "Coming soon". One
   row per user, lazy-created on first GET.

Both tables key off `users.id` with `ON DELETE CASCADE` so user
deletion drops the prefs without an orphan-row sweep job.
"""

from alembic import op

revision = "022_account_settings_and_assignment"
down_revision = "021_proposal_attachment_views"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- Lead auto-assignment ----------------------------------------
    op.execute(
        "ALTER TABLE assignment_rules "
        "ADD COLUMN IF NOT EXISTS is_default BOOLEAN NOT NULL DEFAULT FALSE"
    )
    # Only one default rule allowed — partial unique index enforces.
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_assignment_rules_one_default "
        "ON assignment_rules ((TRUE)) WHERE is_default = TRUE"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS assignment_log (
            id SERIAL PRIMARY KEY,
            lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
            rule_id INTEGER REFERENCES assignment_rules(id) ON DELETE SET NULL,
            assigned_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            reason VARCHAR(32) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_assignment_log_lead "
        "ON assignment_log (lead_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_assignment_log_rule "
        "ON assignment_log (rule_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_assignment_log_user "
        "ON assignment_log (assigned_user_id)"
    )

    # --- Account Settings: notifications -----------------------------
    # `prefs` JSONB carries the event×channel matrix + digest mode +
    # quiet hours. Keeping it as JSONB (not a relational matrix) lets
    # us add new event types without a migration; trade-off is no
    # SQL-side aggregation, which we don't need for this surface.
    op.execute("""
        CREATE TABLE IF NOT EXISTS user_notification_prefs (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL UNIQUE
                REFERENCES users(id) ON DELETE CASCADE,
            in_app_enabled BOOLEAN NOT NULL DEFAULT TRUE,
            email_enabled BOOLEAN NOT NULL DEFAULT TRUE,
            email_digest VARCHAR(20) NOT NULL DEFAULT 'instant',
            quiet_hours_enabled BOOLEAN NOT NULL DEFAULT FALSE,
            quiet_hours_start VARCHAR(5),
            quiet_hours_end VARCHAR(5),
            event_matrix JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    # --- Account Settings: display / locale --------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS user_preferences (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL UNIQUE
                REFERENCES users(id) ON DELETE CASCADE,
            timezone VARCHAR(64) NOT NULL DEFAULT 'America/Chicago',
            locale VARCHAR(10) NOT NULL DEFAULT 'en-US',
            date_format VARCHAR(20) NOT NULL DEFAULT 'MM/DD/YYYY',
            time_format VARCHAR(5) NOT NULL DEFAULT '12h',
            week_start VARCHAR(10) NOT NULL DEFAULT 'sunday',
            currency_display VARCHAR(8) NOT NULL DEFAULT 'USD',
            theme VARCHAR(10) NOT NULL DEFAULT 'system',
            default_landing VARCHAR(64) NOT NULL DEFAULT '/dashboard',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS user_preferences")
    op.execute("DROP TABLE IF EXISTS user_notification_prefs")
    op.execute("DROP INDEX IF EXISTS ix_assignment_log_user")
    op.execute("DROP INDEX IF EXISTS ix_assignment_log_rule")
    op.execute("DROP INDEX IF EXISTS ix_assignment_log_lead")
    op.execute("DROP TABLE IF EXISTS assignment_log")
    op.execute("DROP INDEX IF EXISTS ux_assignment_rules_one_default")
    op.execute(
        "ALTER TABLE assignment_rules DROP COLUMN IF EXISTS is_default"
    )
