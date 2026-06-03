"""Onboarding v3 — unique template name (S1 seed-idempotency backstop).

Revision ID: 054_onboarding_template_unique
Revises: 053_onboarding_secret_values
Create Date: 2026-06-03

The seed UPSERTs templates by ``name`` (application-only keying) and the editor
disambiguates by it, but nothing stopped an admin from creating a second row
with the same name — a later re-seed would then clobber or double-send. This
adds the DB-level ``uq_onboarding_templates_name`` backstop the model now
declares.

Pre-existing duplicates would block the constraint, so the upgrade FIRST
de-dupes non-destructively: every same-name row except the earliest (lowest id)
is renamed with a ``` (dup <id>)``` suffix (id is unique → the result is
unique; the base name is truncated so the 255-char column never overflows). No
row is deleted — a clobbered admin template stays recoverable under its renamed
title. Real up+down on Postgres; the revision id is 30 chars (≤32, respects the
``alembic_version VARCHAR(32)`` cap — so the literal
``054_onboarding_template_name_unique`` filename can't be the id). Single linear
head → ``054_onboarding_template_unique``.
"""

from alembic import op
from sqlalchemy import text

revision = "054_onboarding_template_unique"
down_revision = "053_onboarding_secret_values"
branch_labels = None
depends_on = None

_CONSTRAINT = "uq_onboarding_templates_name"


def upgrade() -> None:
    # De-dupe BEFORE the constraint: rename every same-name row except the
    # earliest one. ``id`` is unique so the suffixed name is guaranteed unique;
    # ``left(name, 230)`` leaves headroom for the suffix under the 255 cap.
    op.execute(
        text(
            """
            UPDATE onboarding_templates AS t
            SET name = left(t.name, 230) || ' (dup ' || t.id || ')'
            WHERE EXISTS (
                SELECT 1 FROM onboarding_templates AS o
                WHERE o.name = t.name AND o.id < t.id
            )
            """
        )
    )
    op.create_unique_constraint(
        _CONSTRAINT, "onboarding_templates", ["name"]
    )


def downgrade() -> None:
    # Drop the uniqueness backstop. The one-way de-dupe rename is intentionally
    # NOT reversed — the suffixed names remain valid and harmless.
    op.drop_constraint(_CONSTRAINT, "onboarding_templates", type_="unique")
