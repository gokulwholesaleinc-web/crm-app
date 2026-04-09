"""Add soft-delete columns to contacts/companies/leads.

Audit Session 3 §1F: DELETE /api/contacts/{id} was a hard delete, and the
dedup service hard-deleted the secondary row on every merge. Contacts
carry AR ledger history, activities, notes, and email threads — destroying
the row wipes out that history by cascade. Per project rule
``feedback_delete_sales_only.md`` contacts must never be hard-deleted.

This migration adds:

* ``contacts.deleted_at`` (nullable timestamptz, indexed) — tombstone for
  the soft-delete path.
* ``contacts.merged_into_id`` / ``companies.merged_into_id`` /
  ``leads.merged_into_id`` (nullable self-referential FK) — points at the
  surviving primary row after a dedup merge so downstream queries can
  follow the forwarding pointer instead of hitting a dead row.

``status`` columns on all three tables are ``String(20)`` already, so the
new ``"archived"`` and ``"merged"`` values require no type change.

Revision ID: 003_contact_soft_delete
Revises: 003_audit_s2
Create Date: 2026-04-09

Chained after ``003_audit_s2`` (the Session 2 webhook_events / public_token
migration) so alembic stays on a single linear head. Both migrations
originally targeted ``002_google_oauth`` as their parent when authored on
independent branches; this file is the later of the two and takes the
merge-point slot.
"""

from alembic import op
import sqlalchemy as sa


revision = "003_contact_soft_delete"
down_revision = "003_audit_s2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "contacts",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_contacts_deleted_at",
        "contacts",
        ["deleted_at"],
    )
    op.add_column(
        "contacts",
        sa.Column(
            "merged_into_id",
            sa.Integer(),
            sa.ForeignKey("contacts.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "companies",
        sa.Column(
            "merged_into_id",
            sa.Integer(),
            sa.ForeignKey("companies.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "leads",
        sa.Column(
            "merged_into_id",
            sa.Integer(),
            sa.ForeignKey("leads.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("leads", "merged_into_id")
    op.drop_column("companies", "merged_into_id")
    op.drop_column("contacts", "merged_into_id")
    op.drop_index("ix_contacts_deleted_at", table_name="contacts")
    op.drop_column("contacts", "deleted_at")
