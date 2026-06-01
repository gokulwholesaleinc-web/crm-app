"""No-mock tests for the PII-scrub + lifecycle-sweep paths (build-order §7).

Covers lazy expiry (writable packet past its TTL → scrub values + signature
and the public gateway 410s), the interim list-time sweep aging
``completion_failed`` → ``abandoned`` past the 7-day window, the
abandoned-state 410, and resend-completion-notice idempotency (a 2nd call adds
NO duplicate EmailQueue row). E-mail is asserted as queued rows, never sent.

These tests drive the scrub LOGIC by setting past timestamps on the live ORM
object (so the sweep's comparison runs). The naive-vs-aware datetime handling
itself is covered by ``test_list_route_omits_access_url`` in
test_onboarding_packets.py (a regression guard for the ``_ensure_aware`` fix).
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from src.email.models import EmailQueue
from src.onboarding import completion, storage, tokens
from src.onboarding.packet_errors import PacketGoneError, PacketRaceError
from src.onboarding.packet_service import (
    COMPLETION_FAILED_RETENTION,
    PacketService,
)

from ._onboarding_helpers import (
    cleanup_packet_storage,
    make_template,
    text_field,
)

pytestmark = pytest.mark.asyncio

RECIPIENT = "client@example.com"


async def _packet(db_session, contact_id, *, created_by_id=None):
    template = await make_template(
        db_session, field_definitions=[text_field("name")]
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
    """
    from fastapi import HTTPException

    from src.core.constants import HTTPStatus
    from src.onboarding.public_helpers import load_packet_for_public

    service, packet, raw = await _packet(db_session, test_contact.id)
    pdf_paths = [d.pdf_path for d in await service.load_documents(packet.id)]
    # Set the TTL in the past on the live (aware) object.
    packet.token_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await db_session.flush()
    try:
        with pytest.raises(HTTPException) as exc_info:
            await load_packet_for_public(db_session, raw)
        assert exc_info.value.status_code == HTTPStatus.GONE  # 410

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
    pdf_paths = [d.pdf_path for d in await service.load_documents(packet.id)]
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
    pdf_paths = [d.pdf_path for d in await service.load_documents(packet.id)]
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
    pdf_paths = [d.pdf_path for d in await service.load_documents(packet.id)]
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
# resend-completion-notice idempotency
# --------------------------------------------------------------------------


async def test_resend_completion_notice_is_idempotent(
    db_session, test_contact, test_user
):
    """A 2nd resend adds NO duplicate EmailQueue row for the same recipient."""
    service, packet, raw = await _packet(
        db_session, test_contact.id, created_by_id=test_user.id
    )
    try:
        # Mark completed so resend is meaningful.
        packet.status = "completed"
        packet.completed_at = datetime.now(UTC)
        await db_session.commit()

        first = await completion.resend_completion_notices(db_session, packet=packet)
        await db_session.commit()
        # Owner (test_user) + client are both queued on the first call.
        assert RECIPIENT in first
        assert test_user.email in first

        count_after_first = await db_session.execute(
            select(func.count())
            .select_from(EmailQueue)
            .where(EmailQueue.entity_type == "onboarding_packets")
            .where(EmailQueue.entity_id == packet.id)
        )
        n1 = count_after_first.scalar()

        # Second resend must be a no-op (rows already exist, non-failed).
        second = await completion.resend_completion_notices(db_session, packet=packet)
        await db_session.commit()
        assert second == []  # nothing newly queued

        count_after_second = await db_session.execute(
            select(func.count())
            .select_from(EmailQueue)
            .where(EmailQueue.entity_type == "onboarding_packets")
            .where(EmailQueue.entity_id == packet.id)
        )
        assert count_after_second.scalar() == n1  # no duplicates
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
