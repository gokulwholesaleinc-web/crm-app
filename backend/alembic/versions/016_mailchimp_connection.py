"""Add mailchimp_connections table for tenant-level Mailchimp integration.

Revision ID: 016_mailchimp_connection
Revises: 015_contact_email_aliases
Create Date: 2026-05-05
"""

from alembic import op

revision = "016_mailchimp_connection"
down_revision = "015_contact_email_aliases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS mailchimp_connections (
            id SERIAL PRIMARY KEY,
            tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            api_key TEXT NOT NULL,
            server_prefix VARCHAR(16) NOT NULL,
            default_audience_id VARCHAR(64),
            default_audience_name VARCHAR(255),
            account_email VARCHAR(255),
            account_login_id VARCHAR(255),
            connected_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            connected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            revoked_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE UNIQUE INDEX ix_mailchimp_connections_tenant
        ON mailchimp_connections (tenant_id)
        WHERE revoked_at IS NULL
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS mailchimp_connections")
