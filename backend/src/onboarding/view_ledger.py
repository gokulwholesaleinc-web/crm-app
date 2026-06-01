"""Per-token document-view ledger for onboarding packets.

Clone of ``proposals.attachment_views`` for the packet read-before-sign
gate: the recipient must open each document from the public link before
``/complete`` accepts the packet. Rows are keyed on the SHA-256 hash of the
access token so a forwarded link can't piggyback on another link's "viewed"
rows, and the insert is SAVEPOINT-idempotent so two concurrent views under
the same token don't 500 the outer transaction.
"""

from __future__ import annotations

import hashlib

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.onboarding.models import (
    OnboardingPacketDocument,
    OnboardingPacketDocumentView,
)


def _hash_token(token: str) -> str:
    """SHA-256 of the access token, lowercased hex (the ledger dedup key)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def record_packet_document_view(
    db: AsyncSession,
    *,
    packet_document_id: int,
    token: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> bool:
    """Idempotently record a public-link view for ``packet_document_id``.

    Returns ``True`` if this call inserted a NEW view row (i.e. the first
    view under this token), ``False`` if a concurrent/earlier view already
    recorded it. The SAVEPOINT contains the UNIQUE-constraint conflict so
    the outer transaction (and any prior reads) survives.
    """
    view = OnboardingPacketDocumentView(
        packet_document_id=packet_document_id,
        token_hash=_hash_token(token),
        ip_address=ip_address,
        user_agent=user_agent,
    )
    try:
        async with db.begin_nested():
            db.add(view)
    except IntegrityError:
        # Already viewed under this token — no-op (documented contract).
        return False
    return True


async def get_unviewed_packet_document_ids(
    db: AsyncSession,
    *,
    packet_id: int,
    token: str,
) -> list[int]:
    """Return packet-document ids NOT yet opened under ``token``.

    An empty list means every document in the packet has been opened from
    this public link at least once — the read-before-sign gate is satisfied.
    """
    token_hash = _hash_token(token)
    rows = await db.execute(
        select(OnboardingPacketDocument.id).where(
            OnboardingPacketDocument.packet_id == packet_id
        )
    )
    document_ids = [r[0] for r in rows.all()]
    if not document_ids:
        return []

    viewed = await db.execute(
        select(OnboardingPacketDocumentView.packet_document_id)
        .where(OnboardingPacketDocumentView.token_hash == token_hash)
        .where(OnboardingPacketDocumentView.packet_document_id.in_(document_ids))
    )
    viewed_ids = {r[0] for r in viewed.all()}
    return [doc_id for doc_id in document_ids if doc_id not in viewed_ids]
