"""Make leads.first_name and leads.last_name nullable.

Company-only leads (imported from CSV without a contact person) have no
first/last name — only a company_name and website. The NOT NULL constraint
on these columns caused CSV imports to fail with IntegrityError for every
row that lacked a contact name.

Revision ID: 004_lead_nullable_names
Revises: 003_contact_soft_delete
Create Date: 2026-04-10
"""

from alembic import op


revision = "004_lead_nullable_names"
down_revision = "003_contact_soft_delete"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("leads", "first_name", nullable=True)
    op.alter_column("leads", "last_name", nullable=True)


def downgrade() -> None:
    op.execute("UPDATE leads SET first_name = '' WHERE first_name IS NULL")
    op.execute("UPDATE leads SET last_name = '' WHERE last_name IS NULL")
    op.alter_column("leads", "first_name", nullable=False)
    op.alter_column("leads", "last_name", nullable=False)
