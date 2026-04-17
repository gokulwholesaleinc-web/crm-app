"""Audit Session 2 schema changes.

Creates the webhook_events idempotency table, adds public_token columns
to quotes + proposals (unique, nullable, backfilled), and relaxes
subscriptions.price_id to nullable so Stripe-initiated subscriptions
(where we don't have a matching local Price row) can be created.

Revision ID: 003_audit_s2
Revises: 002_google_oauth
Create Date: 2026-04-08
"""

import secrets

import sqlalchemy as sa

from alembic import op

revision = "003_audit_s2"
down_revision = "002_google_oauth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -------------------------------------------------------------------
    # webhook_events: persistent Stripe idempotency log
    # -------------------------------------------------------------------
    op.create_table(
        "webhook_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("event_id", sa.String(255), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_webhook_events_event_id",
        "webhook_events",
        ["event_id"],
        unique=True,
    )

    # -------------------------------------------------------------------
    # quotes.public_token: unguessable handle for the public accept flow
    # -------------------------------------------------------------------
    op.add_column(
        "quotes",
        sa.Column("public_token", sa.String(64), nullable=True),
    )
    op.create_index(
        "ix_quotes_public_token",
        "quotes",
        ["public_token"],
        unique=True,
        postgresql_where=sa.text("public_token IS NOT NULL"),
    )

    # -------------------------------------------------------------------
    # proposals.public_token: same treatment
    # -------------------------------------------------------------------
    op.add_column(
        "proposals",
        sa.Column("public_token", sa.String(64), nullable=True),
    )
    op.create_index(
        "ix_proposals_public_token",
        "proposals",
        ["public_token"],
        unique=True,
        postgresql_where=sa.text("public_token IS NOT NULL"),
    )

    # -------------------------------------------------------------------
    # Backfill: every existing quote/proposal gets a fresh token. Run one
    # UPDATE per row so each token is unique. In prod the row count is
    # small at the time of the fix; if it grows we'd switch to a SQL-side
    # generator (gen_random_bytes on Postgres).
    # -------------------------------------------------------------------
    connection = op.get_bind()

    quote_rows = connection.execute(
        sa.text("SELECT id FROM quotes WHERE public_token IS NULL")
    ).fetchall()
    for (quote_id,) in quote_rows:
        connection.execute(
            sa.text("UPDATE quotes SET public_token = :tok WHERE id = :id"),
            {"tok": secrets.token_urlsafe(32), "id": quote_id},
        )

    proposal_rows = connection.execute(
        sa.text("SELECT id FROM proposals WHERE public_token IS NULL")
    ).fetchall()
    for (proposal_id,) in proposal_rows:
        connection.execute(
            sa.text("UPDATE proposals SET public_token = :tok WHERE id = :id"),
            {"tok": secrets.token_urlsafe(32), "id": proposal_id},
        )

    # -------------------------------------------------------------------
    # subscriptions.price_id: relax to nullable so webhook-driven
    # subscription creation can insert rows without a matching local
    # Price row. New subscriptions from Stripe Checkout (where we don't
    # own the Price) will just store the stripe_subscription_id + status.
    # -------------------------------------------------------------------
    op.alter_column(
        "subscriptions",
        "price_id",
        existing_type=sa.Integer(),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "subscriptions",
        "price_id",
        existing_type=sa.Integer(),
        nullable=False,
    )
    op.drop_index("ix_proposals_public_token", table_name="proposals")
    op.drop_column("proposals", "public_token")
    op.drop_index("ix_quotes_public_token", table_name="quotes")
    op.drop_column("quotes", "public_token")
    op.drop_index("ix_webhook_events_event_id", table_name="webhook_events")
    op.drop_table("webhook_events")
