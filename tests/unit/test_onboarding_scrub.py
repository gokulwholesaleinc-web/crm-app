"""No-mock tests for the PII-scrub + lifecycle-sweep paths (build-order §7).

Covers lazy expiry (writable packet past its TTL → scrub values + signature
and the public gateway 410s), the interim list-time sweep aging
``completion_failed`` → ``abandoned`` past the 7-day window, the
abandoned-state 410, and resend-completion-notice (which re-mints a FRESH,
working download link each call). E-mail is asserted as queued rows, never sent.

These tests drive the scrub LOGIC by setting past timestamps on the live ORM
object (so the sweep's comparison runs). The naive-vs-aware datetime handling
itself is covered by ``test_list_route_omits_access_url`` in
test_onboarding_packets.py (a regression guard for the ``_ensure_aware`` fix).
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from src.email.models import EmailQueue
from src.onboarding import completion, storage, tokens
from src.onboarding.packet_errors import PacketGoneError, PacketRaceError
from src.onboarding.packet_service import (
    COMPLETION_FAILED_RETENTION,
    PacketService,
)

from ._onboarding_helpers import (
    cleanup_packet_storage,
    make_questionnaire_template,
    questionnaire_field,
)

pytestmark = pytest.mark.asyncio

RECIPIENT = "client@example.com"


async def _packet(db_session, contact_id, *, created_by_id=None):
    # A generic non-e-sign lifecycle packet (these tests force status directly and
    # never run a real signing flow), so a questionnaire is the simplest send-ready
    # template under the signature-aware e-sign guard.
    template = await make_questionnaire_template(
        db_session, field_definitions=[questionnaire_field("name")]
    )
    service = PacketService(db_session)
    packet, raw = await service.create_packet(
        created_by_id=created_by_id,
        contact_id=contact_id,
        recipient_email=RECIPIENT,
        template_ids=[template.id],
    )
    # Seed some PII to prove it gets scrubbed.
    docs = await service.load_documents(packet.id)
    docs[0].field_values = {"name": "Jane Client"}
    packet.signer_signature_image = b"\x89PNG\r\n\x1a\nfake-signature-bytes"
    await db_session.flush()
    return service, packet, raw


# --------------------------------------------------------------------------
# Lazy expiry (public gateway)
# --------------------------------------------------------------------------


async def test_lazy_expiry_scrubs_and_410s(db_session, test_contact):
    """A writable packet past its TTL flips to expired, scrubs, and 410s.

    Exercises the public gateway resolver directly (same session, no ASGI
    boundary) so the scrub side effect is observable on the live objects.

    Durability guard (§12): the resolver COMMITS the flip + scrub before
    raising the 410, so the side effect survives. ``get_db`` only commits a
    request on SUCCESS — an HTTPException (neither OSError nor SQLAlchemyError)
    skips that commit and the ``finally: close()`` would roll a mere ``flush()``
    back, recomputing (and re-discarding) the scrub on every hit. After a real
    ``commit()`` the session is no longer mid-transaction, which is what we
    assert below (a ``flush()`` would leave it open).
    """
    from fastapi import HTTPException
    from src.core.constants import HTTPStatus
    from src.onboarding.public_helpers import load_packet_for_public

    service, packet, raw = await _packet(db_session, test_contact.id)
    pdf_paths = [
        d.pdf_path for d in await service.load_documents(packet.id) if d.pdf_path
    ]
    # Set the TTL in the past on the live (aware) object.
    packet.token_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await db_session.flush()
    try:
        with pytest.raises(HTTPException) as exc_info:
            await load_packet_for_public(db_session, raw)
        assert exc_info.value.status_code == HTTPStatus.GONE  # 410

        # The flip + scrub were COMMITTED (durable), not merely flushed: the
        # session is no longer in a transaction. (expire_on_commit=False on the
        # test session keeps the in-memory attrs readable below without a query.)
        assert not db_session.in_transaction()

        # The packet was flipped to expired + scrubbed in place.
        assert packet.status == "expired"
        assert packet.signer_signature_image is None
        for doc in await service.load_documents(packet.id):
            assert doc.field_values == {}
    finally:
        for p in pdf_paths:
            await storage.delete(p)


# --------------------------------------------------------------------------
# List-time sweep: completion_failed -> abandoned past the retention window
# --------------------------------------------------------------------------


async def test_list_sweep_ages_completion_failed_to_abandoned(
    db_session, test_contact
):
    """A completion_failed packet older than the window ages to abandoned."""
    service, packet, raw = await _packet(db_session, test_contact.id)
    pdf_paths = [
        d.pdf_path for d in await service.load_documents(packet.id) if d.pdf_path
    ]
    try:
        # Put it in completion_failed with a stale claim timestamp (aware, past
        # the 7-day retention window).
        packet.status = "completion_failed"
        packet.completing_since = (
            datetime.now(UTC) - COMPLETION_FAILED_RETENTION - timedelta(days=1)
        )
        # Keep the TTL in the future so the expiry branch doesn't fire first.
        packet.token_expires_at = datetime.now(UTC) + timedelta(days=10)
        await db_session.flush()

        packets = await service.list_packets(test_contact.id)
        aged = next(p for p in packets if p.id == packet.id)
        assert aged.status == "abandoned"
        assert aged.abandoned_at is not None
        # PII scrubbed on the transition.
        assert aged.signer_signature_image is None
        for doc in await service.load_documents(packet.id):
            assert doc.field_values == {}
    finally:
        for p in pdf_paths:
            await storage.delete(p)


async def test_list_sweep_keeps_recent_completion_failed(db_session, test_contact):
    """A recently-failed packet is NOT aged to abandoned by the sweep."""
    service, packet, raw = await _packet(db_session, test_contact.id)
    pdf_paths = [
        d.pdf_path for d in await service.load_documents(packet.id) if d.pdf_path
    ]
    try:
        packet.status = "completion_failed"
        packet.completing_since = datetime.now(UTC) - timedelta(hours=1)  # recent
        packet.token_expires_at = datetime.now(UTC) + timedelta(days=10)
        await db_session.flush()

        packets = await service.list_packets(test_contact.id)
        still = next(p for p in packets if p.id == packet.id)
        assert still.status == "completion_failed"  # retry window still open
    finally:
        for p in pdf_paths:
            await storage.delete(p)


# --------------------------------------------------------------------------
# Abandoned terminal state → 410 + retry forbidden
# --------------------------------------------------------------------------


async def test_abandoned_public_access_410(client, db_session, test_contact):
    """An abandoned packet 410s on the public gateway (data purged)."""
    service, packet, raw = await _packet(db_session, test_contact.id)
    pdf_paths = [
        d.pdf_path for d in await service.load_documents(packet.id) if d.pdf_path
    ]
    packet.status = "abandoned"
    packet.abandoned_at = datetime.now(UTC)
    await db_session.commit()
    try:
        resp = await client.get(f"/api/onboarding/public/{raw}")
        assert resp.status_code == 410
    finally:
        for p in pdf_paths:
            await storage.delete(p)


async def test_retry_completion_refused_when_abandoned(db_session, test_contact):
    """retry_completion is refused (410) once the packet is abandoned."""
    service, packet, raw = await _packet(db_session, test_contact.id)
    try:
        packet.status = "abandoned"
        await db_session.flush()
        with pytest.raises(PacketGoneError):
            await completion.retry_completion(db_session, packet=packet)
    finally:
        await cleanup_packet_storage(db_session, service, packet.id)


# --------------------------------------------------------------------------
# resend-completion-notice — re-mints a working download link
# --------------------------------------------------------------------------


async def test_resend_completion_notice_remints_working_link(
    db_session, test_contact, test_user
):
    """Resend mints a FRESH download token + e-mails a real, resolvable link.

    The raw download token from completion is unrecoverable (only its hash is
    stored), so resend rotates it and embeds the new ``/onboarding/complete/
    <token>`` link rather than the old linkless "contact us" body. The emailed
    link must hash to the packet's stored ``download_token_hash`` (i.e. it
    actually works). Resend is a deliberate staff re-delivery, so a 2nd call
    rotates the token again and re-queues (it is not suppressed).
    """
    import re

    service, packet, raw = await _packet(
        db_session, test_contact.id, created_by_id=test_user.id
    )
    try:
        packet.status = "completed"
        packet.completed_at = datetime.now(UTC)
        await db_session.commit()

        first = await completion.resend_completion_notices(db_session, packet=packet)
        await db_session.commit()
        # Owner (test_user) + client are both queued on the first call.
        assert RECIPIENT in first
        assert test_user.email in first

        await db_session.refresh(packet)
        token_after_first = packet.download_token_hash
        assert token_after_first  # a real download token was minted
        assert packet.download_token_expires_at is not None

        # The client e-mail carries a working /onboarding/complete/<token> link
        # whose raw token hashes to the stored download_token_hash.
        client_row = (
            await db_session.execute(
                select(EmailQueue)
                .where(EmailQueue.entity_type == "onboarding_packets")
                .where(EmailQueue.entity_id == packet.id)
                .where(EmailQueue.to_email == RECIPIENT)
                .order_by(EmailQueue.id.desc())
            )
        ).scalars().first()
        assert "contact us" not in client_row.body.lower()
        # Resent notice is attributed to the packet owner (no fallback sender).
        assert client_row.sent_by_id == test_user.id
        match = re.search(r"/onboarding/complete/(\S+)", client_row.body)
        assert match, client_row.body
        assert tokens.hash_token(match.group(1)) == packet.download_token_hash

        # A 2nd resend rotates the token (old link dies) and re-queues.
        second = await completion.resend_completion_notices(db_session, packet=packet)
        await db_session.commit()
        assert RECIPIENT in second
        await db_session.refresh(packet)
        assert packet.download_token_hash != token_after_first
    finally:
        await cleanup_packet_storage(db_session, service, packet.id)


async def test_resend_completion_notice_refused_when_not_completed(
    db_session, test_contact
):
    """resend is a 409 (PacketRaceError) when the packet isn't completed."""
    service, packet, raw = await _packet(db_session, test_contact.id)
    try:
        with pytest.raises(PacketRaceError):
            await completion.resend_completion_notices(db_session, packet=packet)
    finally:
        await cleanup_packet_storage(db_session, service, packet.id)
