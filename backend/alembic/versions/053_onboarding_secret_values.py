"""Onboarding v3 — encrypted sensitive-text values (F4 passwords).

The dedicated ciphertext table the §A.4 forward-design left deferred. The 5
decisions block (§F, CONFIRMED 2026-06-03, decision #1) REVERSES the "zero
rows / deferred" stance: F4 passwords are COLLECTED + ENCRYPTED AT REST, so
this table SHIPS in v1 and WILL have rows. A ``sensitive: true`` text field's
plaintext never enters ``field_values`` JSONB nor any generated PDF — only the
Fernet ciphertext (here) does, keyed by ``ONBOARDING_FIELD_KEY`` (NOT
``SECRET_KEY``; see ``onboarding/crypto.py``).

One row per (packet_document_id, field_id) — the composite PK is the upsert
target ``packet_service.patch_document`` writes to in the SAME txn as the
version bump. ``ON DELETE CASCADE`` on the document FK so a packet teardown
drops the ciphertext; ``scrub_packet`` ALSO deletes these rows explicitly on
every terminal transition (kind-agnostic — any doc may carry a sensitive
field), so a secret is gone even before the cascade fires.

Integer FK (matches the existing Integer PKs on
``onboarding_packet_documents`` — NOT BigInteger). Single linear head;
``down_revision = "052_onboarding_typed_docs"``; revision id is 28 chars
(≤32, respects the ``alembic_version VARCHAR(32)`` cap). Real up+down on
Postgres.
"""

import sqlalchemy as sa

from alembic import op

revision = "053_onboarding_secret_values"
down_revision = "052_onboarding_typed_docs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "onboarding_secret_values",
        sa.Column("packet_document_id", sa.Integer(), nullable=False),
        # Which sensitive question this ciphertext answers.
        sa.Column("field_id", sa.String(length=64), nullable=False),
        # Fernet token (AES-128-CBC + HMAC); never the plaintext.
        sa.Column("ciphertext", sa.LargeBinary(), nullable=False),
        # Key generation that encrypted this token (rotation support).
        sa.Column(
            "key_version", sa.SmallInteger(), server_default="1", nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["packet_document_id"],
            ["onboarding_packet_documents.id"],
            name="fk_onboarding_secret_values_document_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "packet_document_id",
            "field_id",
            name="pk_onboarding_secret_values",
        ),
    )


def downgrade() -> None:
    op.drop_table("onboarding_secret_values")
