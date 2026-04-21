"""NULL out empty-string Gmail thread_id / message_id values.

Earlier code stored `""` when Gmail omitted the field. Those rows pass
`IS NOT NULL` filters and break thread-context lookups.

Revision ID: 008_null_empty_email_thread_ids
Revises: 007_gmail_connections
Create Date: 2026-04-21
"""

from alembic import op

revision = "008_null_empty_email_thread_ids"
down_revision = "007_gmail_connections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE email_queue SET thread_id = NULL WHERE thread_id = ''")
    op.execute("UPDATE email_queue SET message_id = NULL WHERE message_id = ''")
    op.execute("UPDATE inbound_emails SET thread_id = NULL WHERE thread_id = ''")
    op.execute("UPDATE inbound_emails SET message_id = NULL WHERE message_id = ''")
    op.execute("UPDATE inbound_emails SET in_reply_to = NULL WHERE in_reply_to = ''")


def downgrade() -> None:
    # Lossless NULL→"" is undesirable; no-op downgrade keeps rows clean.
    pass
