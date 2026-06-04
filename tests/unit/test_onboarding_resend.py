"""No-mock tests for the staff invite-resend endpoint + service (§C.2).

Asserts the status rules (allowed for active/opened/in_progress/expired, 409
for completed/revoked/completing/abandoned), a FRESH access token on resend,
the expired→fresh-restart (status flips back to active), and that a new invite
``EmailQueue`` row is queued (deliberate staff action, not idempotency-suppressed).

E-mail side effects are asserted as ``EmailQueue`` rows, never a live send.
"""

import pytest
from sqlalchemy import select
from src.email.models import EmailQueue
from src.onboarding import tokens
from src.onboarding.completion_notices import INVITE_SUBJECT
from src.onboarding.packet_errors import PacketRaceError
from src.onboarding.packet_service import PacketService

from ._onboarding_helpers import cleanup_packet_storage, make_template

pytestmark = pytest.mark.asyncio

RECIPIENT = "client@example.com"


async def _make_packet(db, contact_id, created_by_id):
    template = await make_template(db)
    service = PacketService(db)
    packet, raw = await service.create_packet(
        created_by_id=created_by_id,
        contact_id=contact_id,
        recipient_email=RECIPIENT,
        template_ids=[template.id],
    )
    await db.commit()
    return service, packet, raw


async def _invite_rows(db, packet_id):
    return (
        await db.execute(
            select(EmailQueue)
            .where(EmailQueue.entity_type == "onboarding_packets")
            .where(EmailQueue.entity_id == packet_id)
            .where(EmailQueue.subject == INVITE_SUBJECT)
        )
    ).scalars().all()


# --------------------------------------------------------------------------
# Service-level status rules + fresh token
# --------------------------------------------------------------------------


async def test_resend_invite_mints_fresh_token(db_session, test_contact, test_user):
    """resend_invite rotates the token hash + bumps expiry, returns a new raw token."""
    service, packet, raw = await _make_packet(
        db_session, test_contact.id, test_user.id
    )
    try:
        old_hash = packet.token_hash
        old_exp = packet.token_expires_at
        new_raw = await service.resend_invite(packet, actor_id=test_user.id)
        assert new_raw != raw
        assert packet.token_hash == tokens.hash_token(new_raw)
        assert packet.token_hash != old_hash
        assert packet.token_expires_at >= old_exp
    finally:
        await cleanup_packet_storage(db_session, service, packet.id)


async def test_resend_invite_expired_restarts_active(
    db_session, test_contact, test_user
):
    """An expired packet flips back to active with a fresh token on resend."""
    service, packet, _ = await _make_packet(
        db_session, test_contact.id, test_user.id
    )
    try:
        packet.status = "expired"
        await db_session.flush()
        await service.resend_invite(packet, actor_id=test_user.id)
        assert packet.status == "active"
    finally:
        await cleanup_packet_storage(db_session, service, packet.id)


@pytest.mark.parametrize(
    "status", ["completed", "revoked", "completing", "abandoned"]
)
async def test_resend_invite_refused_for_terminal_statuses(
    db_session, test_contact, test_user, status
):
    """resend_invite is refused (PacketRaceError → 409) for terminal statuses."""
    service, packet, _ = await _make_packet(
        db_session, test_contact.id, test_user.id
    )
    try:
        packet.status = status
        await db_session.flush()
        with pytest.raises(PacketRaceError):
            await service.resend_invite(packet, actor_id=test_user.id)
    finally:
        await cleanup_packet_storage(db_session, service, packet.id)


# --------------------------------------------------------------------------
# Route-level
# --------------------------------------------------------------------------


async def test_resend_route_queues_new_invite(
    client, db_session, test_contact, gmail_connected_test_user, admin_auth_headers
):
    """POST /packets/{id}/resend queues a new invite + returns the packet.

    The owner (``created_by_id``) is Gmail-connected so the F4 pre-flight
    passes — the route sends from the owner's connected account.
    """
    service, packet, _ = await _make_packet(
        db_session, test_contact.id, gmail_connected_test_user.id
    )
    try:
        resp = await client.post(
            f"/api/onboarding/packets/{packet.id}/resend",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["id"] == packet.id
        invites = await _invite_rows(db_session, packet.id)
        assert len(invites) == 1
        assert invites[0].subject == INVITE_SUBJECT
    finally:
        await cleanup_packet_storage(db_session, service, packet.id)


async def test_resend_route_409_for_completed(
    client, db_session, test_contact, gmail_connected_test_user, admin_auth_headers
):
    """The route surfaces the terminal-status refusal as a 409.

    Owner Gmail-connected so the F4 pre-flight passes; the 409 comes from the
    terminal-status guard in ``resend_invite`` (not the Gmail check).
    """
    service, packet, _ = await _make_packet(
        db_session, test_contact.id, gmail_connected_test_user.id
    )
    try:
        packet.status = "completed"
        await db_session.commit()
        resp = await client.post(
            f"/api/onboarding/packets/{packet.id}/resend",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 409, resp.text
    finally:
        await cleanup_packet_storage(db_session, service, packet.id)
