"""Meta token encryption retrofit (C4) — expand phase: add ciphertext columns.

Revision ID: 058_meta_token_encryption
Revises: 057_marketing_phase2_ga4
Create Date: 2026-06-09

EXPAND step of the multi-deploy plaintext→encrypted retrofit for the Meta
integration's stored OAuth token (``meta_credentials.access_token`` is plaintext
today). Additive + safe:

* add ``access_token_ciphertext`` (LargeBinary, nullable) + ``token_key_version``
  (SmallInteger, nullable);
* make the legacy ``access_token`` column NULLABLE so the later contract phase can
  stop writing plaintext.

Deploy order (see meta/service.py + meta/crypto.py):
  1. set META_TOKEN_KEY on the backend, deploy this migration + write-both/
     read-new-fallback-old code (META_TOKEN_ENCRYPTION_STRICT=False);
  2. run backend/scripts/backfill_meta_token_encryption.py (key-guarded, resumable);
  3. flip META_TOKEN_ENCRYPTION_STRICT=True (read-new-only + stop writing plaintext);
  4. LATER, a separate contract migration drops access_token (+ the dead
     page_access_tokens column) — intentionally NOT in this migration so a stray
     ``upgrade head`` can never drop plaintext before the backfill runs.
"""

import sqlalchemy as sa
from alembic import op

revision = "058_meta_token_encryption"
down_revision = "057_marketing_phase2_ga4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "meta_credentials",
        sa.Column("access_token_ciphertext", sa.LargeBinary(), nullable=True),
    )
    op.add_column(
        "meta_credentials",
        sa.Column("token_key_version", sa.SmallInteger(), nullable=True),
    )
    with op.batch_alter_table("meta_credentials") as batch:
        batch.alter_column("access_token", existing_type=sa.Text(), nullable=True)


def downgrade() -> None:
    with op.batch_alter_table("meta_credentials") as batch:
        batch.alter_column("access_token", existing_type=sa.Text(), nullable=False)
    op.drop_column("meta_credentials", "token_key_version")
    op.drop_column("meta_credentials", "access_token_ciphertext")
