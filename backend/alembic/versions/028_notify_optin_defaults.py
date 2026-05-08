"""notification opt-in defaults: flip in_app_enabled + email_enabled to false

Revision ID: 028_notify_optin
Revises: 027_branding_bg
Create Date: 2026-05-08

Switches the notification system from opt-out to opt-in. Previously,
missing prefs rows and missing event_matrix entries both defaulted to ON.
Now they default to OFF — users must explicitly enable notifications in
Settings → Notifications.

Existing rows are flipped to FALSE so that users who have never touched
their notification settings don't start getting emails or bells they
haven't opted into. Column server_defaults are also flipped so any new
rows created without explicit values land opt-out as well.
"""

import sqlalchemy as sa

from alembic import op

revision = "028_notify_optin"
down_revision = "027_branding_bg"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "UPDATE user_notification_prefs SET in_app_enabled = FALSE, email_enabled = FALSE"
    )
    op.alter_column(
        "user_notification_prefs",
        "in_app_enabled",
        server_default=sa.text("false"),
    )
    op.alter_column(
        "user_notification_prefs",
        "email_enabled",
        server_default=sa.text("false"),
    )


def downgrade():
    op.alter_column(
        "user_notification_prefs",
        "email_enabled",
        server_default=sa.text("true"),
    )
    op.alter_column(
        "user_notification_prefs",
        "in_app_enabled",
        server_default=sa.text("true"),
    )
    op.execute(
        "UPDATE user_notification_prefs SET in_app_enabled = TRUE, email_enabled = TRUE"
    )
