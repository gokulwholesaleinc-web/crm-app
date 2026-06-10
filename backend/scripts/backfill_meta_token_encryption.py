"""Backfill encrypted Meta access tokens (C4, step 2 of the multi-deploy retrofit).

Encrypts every ``meta_credentials`` row that still has a plaintext ``access_token``
but no ``access_token_ciphertext``, using ``meta/crypto`` (``META_TOKEN_KEY``).

* Key-guarded: refuses to run unless META_TOKEN_KEY is set (fail closed).
* Resumable + idempotent: only rows with ciphertext IS NULL are touched, so a
  re-run after a partial pass continues where it stopped and a completed pass is a
  no-op. The plaintext column is LEFT in place (the contract phase / a later
  migration removes it) so this step is safe to run before flipping
  META_TOKEN_ENCRYPTION_STRICT.

Usage:
  docker compose exec backend python scripts/backfill_meta_token_encryption.py
  (or)  python scripts/backfill_meta_token_encryption.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import async_session_maker
from src.meta import crypto
from src.meta.models import MetaCredential

logger = logging.getLogger("backfill_meta_token_encryption")


async def backfill_meta_tokens(session: AsyncSession, *, batch_size: int = 100) -> dict[str, int]:
    """Encrypt plaintext tokens lacking ciphertext. Returns {"encrypted": n}.

    Commits per batch. Idempotent + resumable: only non-empty plaintext rows without
    ciphertext are selected, so each batch strictly shrinks the work set (no livelock).
    """
    if not crypto.is_configured():
        raise crypto.MetaCryptoError(
            "META_TOKEN_KEY is not set — refusing to backfill (fail closed)."
        )

    encrypted = 0
    while True:
        rows = (
            (
                await session.execute(
                    select(MetaCredential)
                    .where(
                        MetaCredential.access_token_ciphertext.is_(None),
                        MetaCredential.access_token.isnot(None),
                        # Exclude empty strings: '' satisfies IS NOT NULL, and we skip
                        # encrypting it, so without this filter such a row would be
                        # re-selected every iteration → livelock. (No token to encrypt.)
                        func.length(MetaCredential.access_token) > 0,
                    )
                    .limit(batch_size)
                )
            )
            .scalars()
            .all()
        )
        if not rows:
            break
        for cred in rows:
            ct, version = crypto.encrypt_token(cred.access_token)
            cred.access_token_ciphertext = ct
            cred.token_key_version = version
            encrypted += 1
        await session.commit()
        # Every selected row was encrypted, so the NULL-ciphertext set strictly
        # shrinks each batch; the next loop re-queries the now-smaller set.

    return {"encrypted": encrypted}


async def strict_readiness(session: AsyncSession) -> dict[str, int]:
    """Operator gates for the C4 contract steps (C4-4 / C4-5).

    Returns counts that MUST be 0 before the irreversible steps:
      * ``plaintext_only`` — rows readable only via plaintext (ciphertext NULL but
        access_token set). Flipping META_TOKEN_ENCRYPTION_STRICT while >0 makes those
        Meta connections silently unreadable (the runtime fails closed, recoverable).
      * ``nonempty_page_access_tokens`` — rows whose dead page_access_tokens column is
        non-NULL. The future plaintext-DROP migration must NOT run while >0, or those
        are silently-dropped plaintext secrets.
    """
    plaintext_only = (
        await session.execute(
            select(func.count())
            .select_from(MetaCredential)
            .where(
                MetaCredential.access_token_ciphertext.is_(None),
                MetaCredential.access_token.isnot(None),
                func.length(MetaCredential.access_token) > 0,
            )
        )
    ).scalar_one()
    nonempty_pages = (
        await session.execute(
            select(func.count())
            .select_from(MetaCredential)
            .where(MetaCredential.page_access_tokens.isnot(None))
        )
    ).scalar_one()
    return {"plaintext_only": plaintext_only, "nonempty_page_access_tokens": nonempty_pages}


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    async with async_session_maker() as session:
        result = await backfill_meta_tokens(session)
        gates = await strict_readiness(session)
    logger.info("Meta token backfill complete: %d encrypted", result["encrypted"])
    logger.info(
        "STRICT-readiness: %d plaintext-only remaining (must be 0 before flipping "
        "META_TOKEN_ENCRYPTION_STRICT); %d non-empty page_access_tokens (must be 0 "
        "before the plaintext-drop migration).",
        gates["plaintext_only"], gates["nonempty_page_access_tokens"],
    )
    if gates["plaintext_only"]:
        logger.warning("NOT STRICT-ready: %d Meta credential(s) still plaintext-only.", gates["plaintext_only"])


if __name__ == "__main__":
    asyncio.run(main())
