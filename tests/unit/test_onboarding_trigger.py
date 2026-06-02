"""No-mock tests for the Phase-3 auto-send trigger (§B/§C).

Drives the real admin + public proposal-accept routes and asserts that a
packet + invite ``EmailQueue`` row materialize when the proposal has active
onboarding selections, that the failure modes (no contact / no recipient
email / create_packet error) land on a durable proposal ``Activity`` row WITHOUT
500-ing the accept, that empty selections mint no packet, and that the invite
is idempotent (a non-failed row suppresses, a failed row allows a resend).

E-mail side effects are asserted as ``EmailQueue`` rows + status, never a live
send. No mocks.
"""

import secrets

import pytest
from sqlalchemy import select
from src.activities.models import Activity
from src.email.models import EmailQueue
from src.onboarding.completion_notices import INVITE_SUBJECT, queue_invite
from src.onboarding.models import OnboardingPacket
from src.onboarding.packet_service import PacketService
from src.onboarding.selection_service import SelectionService
from src.proposals.models import Proposal

from ._onboarding_helpers import cleanup_packet_storage, make_template

pytestmark = pytest.mark.asyncio


async def _make_sent_proposal(
    db, owner_id, *, contact_id=None, company_id=None, designated_signer_email=None
):
    proposal = Proposal(
        proposal_number=f"PR-TRG-{secrets.token_hex(4)}",
        title="Trigger Proposal",
        status="sent",
        owner_id=owner_id,
        created_by_id=owner_id,
        contact_id=contact_id,
        company_id=company_id,
        designated_signer_email=designated_signer_email,
    )
    db.add(proposal)
    await db.commit()
    await db.refresh(proposal)
    return proposal


async def _select(db, proposal_id, template_ids, owner_id):
    await SelectionService(db).set_selections(
        proposal_id, template_ids=template_ids, actor_id=owner_id
    )
    await db.commit()


async def _packets_for_proposal(db, proposal_id):
    return (
        await db.execute(
            select(OnboardingPacket).where(
                OnboardingPacket.proposal_id == proposal_id
            )
        )
    ).scalars().all()


async def _invite_rows(db, packet_id):
    return (
        await db.execute(
            select(EmailQueue)
            .where(EmailQueue.entity_type == "onboarding_packets")
            .where(EmailQueue.entity_id == packet_id)
            .where(EmailQueue.subject == INVITE_SUBJECT)
        )
    ).scalars().all()


async def _skip_activities(db, proposal_id):
    return (
        await db.execute(
            select(Activity)
            .where(Activity.entity_type == "proposals")
            .where(Activity.entity_id == proposal_id)
            .where(Activity.subject == "Onboarding auto-send skipped")
        )
    ).scalars().all()


# --------------------------------------------------------------------------
# Admin accept → packet + invite
# --------------------------------------------------------------------------


async def test_admin_accept_creates_packet_and_invite(
    client, db_session, test_admin_user, test_contact, admin_auth_headers
):
    """Admin accept of a proposal with selections mints a packet + invite row."""
    proposal = await _make_sent_proposal(
        db_session, test_admin_user.id, contact_id=test_contact.id
    )
    template = await make_template(db_session)
    await _select(db_session, proposal.id, [template.id], test_admin_user.id)

    resp = await client.post(
        f"/api/proposals/{proposal.id}/accept", headers=admin_auth_headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "accepted"

    packets = await _packets_for_proposal(db_session, proposal.id)
    assert len(packets) == 1
    packet = packets[0]
    try:
        assert packet.recipient_email == test_contact.email
        invites = await _invite_rows(db_session, packet.id)
        assert len(invites) == 1
        assert invites[0].to_email == test_contact.email
        # The invite MUST be attributed to the packet owner — outbound mail has
        # no fallback sender, so a NULL sent_by_id can only ever fail to deliver.
        assert invites[0].sent_by_id == test_admin_user.id
        assert packet.created_by_id == test_admin_user.id
    finally:
        await cleanup_packet_storage(db_session, PacketService(db_session), packet.id)


async def test_public_accept_creates_packet_and_invite(
    client, db_session, test_user, test_contact
):
    """Public sign-to-confirm accept also fires the trigger (no event bus)."""
    proposal = await _make_sent_proposal(
        db_session, test_user.id, contact_id=test_contact.id
    )
    proposal.public_token = secrets.token_urlsafe(32)
    proposal.designated_signer_email = test_contact.email
    await db_session.commit()
    template = await make_template(db_session)
    await _select(db_session, proposal.id, [template.id], test_user.id)

    import base64

    from ._onboarding_helpers import png_bytes

    sig_b64 = base64.b64encode(png_bytes()).decode("ascii")
    resp = await client.post(
        f"/api/proposals/public/{proposal.public_token}/accept",
        json={
            "signer_name": "Jane Client",
            "signer_email": test_contact.email,
            "signature_image": sig_b64,
            "agreed_to_terms": True,
        },
    )
    assert resp.status_code == 200, resp.text

    packets = await _packets_for_proposal(db_session, proposal.id)
    assert len(packets) == 1
    packet = packets[0]
    try:
        invites = await _invite_rows(db_session, packet.id)
        assert len(invites) == 1
        # Attributed to the proposal owner so it can actually send (no fallback).
        assert invites[0].sent_by_id == test_user.id
    finally:
        await cleanup_packet_storage(db_session, PacketService(db_session), packet.id)


async def test_accept_with_no_selections_creates_no_packet(
    client, db_session, test_admin_user, test_contact, admin_auth_headers
):
    """A proposal with zero onboarding selections mints no packet (no-op)."""
    proposal = await _make_sent_proposal(
        db_session, test_admin_user.id, contact_id=test_contact.id
    )
    resp = await client.post(
        f"/api/proposals/{proposal.id}/accept", headers=admin_auth_headers
    )
    assert resp.status_code == 200, resp.text
    assert await _packets_for_proposal(db_session, proposal.id) == []


# --------------------------------------------------------------------------
# Failure modes → durable Activity, never a 500 on the accept
# --------------------------------------------------------------------------


async def test_accept_no_contact_writes_activity_no_packet(
    client, db_session, test_admin_user, admin_auth_headers
):
    """No linked contact → accept still succeeds; a skip Activity is written."""
    proposal = await _make_sent_proposal(db_session, test_admin_user.id)
    template = await make_template(db_session)
    await _select(db_session, proposal.id, [template.id], test_admin_user.id)

    resp = await client.post(
        f"/api/proposals/{proposal.id}/accept", headers=admin_auth_headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "accepted"
    assert await _packets_for_proposal(db_session, proposal.id) == []
    acts = await _skip_activities(db_session, proposal.id)
    assert len(acts) == 1
    assert "no linked contact" in acts[0].description


async def test_accept_no_recipient_email_writes_activity_no_packet(
    client, db_session, test_admin_user, test_company, admin_auth_headers
):
    """A contact with no email + no designated signer → skip Activity, no packet."""
    from src.contacts.models import Contact

    contact = Contact(
        first_name="No",
        last_name="Email",
        email=None,
        company_id=test_company.id,
        status="active",
        owner_id=test_admin_user.id,
        created_by_id=test_admin_user.id,
    )
    db_session.add(contact)
    await db_session.commit()
    await db_session.refresh(contact)

    proposal = await _make_sent_proposal(
        db_session, test_admin_user.id, contact_id=contact.id
    )
    template = await make_template(db_session)
    await _select(db_session, proposal.id, [template.id], test_admin_user.id)

    resp = await client.post(
        f"/api/proposals/{proposal.id}/accept", headers=admin_auth_headers
    )
    assert resp.status_code == 200, resp.text
    assert await _packets_for_proposal(db_session, proposal.id) == []
    acts = await _skip_activities(db_session, proposal.id)
    assert len(acts) == 1
    assert "recipient email" in acts[0].description


async def test_accept_no_owner_writes_activity_no_packet(
    client, db_session, test_admin_user, test_contact, admin_auth_headers
):
    """An owner-less proposal mints NO packet — the invite would queue with
    sent_by_id=None (no fallback sender → permanent send failure) and be
    invisible to every non-admin in the email queue. A skip Activity records
    the reason instead, and the accept still returns 200.
    """
    # owner_id=None → no connected Gmail to send the invite from.
    proposal = await _make_sent_proposal(
        db_session, None, contact_id=test_contact.id
    )
    template = await make_template(db_session)
    # Selections must be set by a real actor even though the proposal is ownerless.
    await _select(db_session, proposal.id, [template.id], test_admin_user.id)

    resp = await client.post(
        f"/api/proposals/{proposal.id}/accept", headers=admin_auth_headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "accepted"
    assert await _packets_for_proposal(db_session, proposal.id) == []
    acts = await _skip_activities(db_session, proposal.id)
    assert len(acts) == 1
    assert "no owner" in acts[0].description


async def test_trigger_never_500s_the_accept_on_create_packet_error(
    client, db_session, test_admin_user, test_contact, admin_auth_headers
):
    """Force a create_packet failure (template PDF deleted from storage).

    The accept MUST still return 200 + 'accepted', no packet is left behind,
    and a failure Activity row records the reason.
    """
    from src.onboarding import storage

    proposal = await _make_sent_proposal(
        db_session, test_admin_user.id, contact_id=test_contact.id
    )
    template = await make_template(db_session)
    await _select(db_session, proposal.id, [template.id], test_admin_user.id)
    # Sabotage: delete the template's source PDF so the per-packet copy read
    # raises inside create_packet → PacketValidationError, caught by the trigger.
    await storage.delete(template.pdf_path)

    resp = await client.post(
        f"/api/proposals/{proposal.id}/accept", headers=admin_auth_headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "accepted"
    assert await _packets_for_proposal(db_session, proposal.id) == []
    acts = await _skip_activities(db_session, proposal.id)
    assert len(acts) == 1
    assert "could not be created" in acts[0].description


# --------------------------------------------------------------------------
# Invite idempotency
# --------------------------------------------------------------------------


async def test_invite_idempotent_non_failed_row_suppresses(
    db_session, test_user, test_contact
):
    """A second auto-send queue_invite is suppressed by a non-failed row."""
    service = PacketService(db_session)
    packet, raw = await service.create_packet(
        created_by_id=test_user.id,
        contact_id=test_contact.id,
        recipient_email=test_contact.email,
        template_ids=[(await make_template(db_session)).id],
    )
    await db_session.commit()
    try:
        first = await queue_invite(db_session, packet=packet, raw_access_token=raw)
        assert first is True
        second = await queue_invite(db_session, packet=packet, raw_access_token=raw)
        assert second is False
        invites = await _invite_rows(db_session, packet.id)
        assert len(invites) == 1
        # The queued invite carries a real sender (the packet owner).
        assert invites[0].sent_by_id == test_user.id
    finally:
        await cleanup_packet_storage(db_session, service, packet.id)


async def test_invite_failed_row_allows_resend(
    db_session, test_user, test_contact
):
    """A previously-failed invite row does NOT suppress a re-queue."""
    service = PacketService(db_session)
    packet, raw = await service.create_packet(
        created_by_id=test_user.id,
        contact_id=test_contact.id,
        recipient_email=test_contact.email,
        template_ids=[(await make_template(db_session)).id],
    )
    await db_session.commit()
    try:
        await queue_invite(db_session, packet=packet, raw_access_token=raw)
        # Mark the existing invite failed → it should no longer suppress.
        rows = await _invite_rows(db_session, packet.id)
        rows[0].status = "failed"
        await db_session.flush()

        again = await queue_invite(db_session, packet=packet, raw_access_token=raw)
        assert again is True
        non_failed = [
            r for r in await _invite_rows(db_session, packet.id) if r.status != "failed"
        ]
        assert len(non_failed) == 1
    finally:
        await cleanup_packet_storage(db_session, service, packet.id)


async def test_completion_notice_not_suppressed_by_invite(
    db_session, test_user, test_contact
):
    """A prior INVITE must not suppress the completion notice to the SAME
    recipient — the idempotency key is per (packet, recipient, subject), so the
    different-subject completion e-mail still queues (and a duplicate of it is
    still suppressed)."""
    from src.email.service import EmailService
    from src.onboarding.completion_notices import _queue_once

    service = PacketService(db_session)
    packet, raw = await service.create_packet(
        created_by_id=test_user.id,
        contact_id=test_contact.id,
        recipient_email=test_contact.email,
        template_ids=[(await make_template(db_session)).id],
    )
    await db_session.commit()
    completion_subject = "Your onboarding documents are ready"
    try:
        # Auto-send invite lands first (same recipient, INVITE subject).
        assert await queue_invite(db_session, packet=packet, raw_access_token=raw)
        # The completion notice (different subject) must STILL queue.
        await _queue_once(
            EmailService(db_session),
            db_session,
            packet_id=packet.id,
            to_email=test_contact.email,
            subject=completion_subject,
            body="download link here",
            sent_by_id=test_user.id,
        )
        await db_session.commit()

        rows = (
            await db_session.execute(
                select(EmailQueue)
                .where(EmailQueue.entity_type == "onboarding_packets")
                .where(EmailQueue.entity_id == packet.id)
                .where(EmailQueue.to_email == test_contact.email)
            )
        ).scalars().all()
        subjects = {r.subject for r in rows}
        assert INVITE_SUBJECT in subjects
        assert completion_subject in subjects
        assert len(rows) == 2  # the invite did NOT suppress the completion notice

        # A duplicate completion notice (same subject) IS still suppressed.
        await _queue_once(
            EmailService(db_session),
            db_session,
            packet_id=packet.id,
            to_email=test_contact.email,
            subject=completion_subject,
            body="download link here",
            sent_by_id=test_user.id,
        )
        await db_session.commit()
        same_subject = (
            await db_session.execute(
                select(EmailQueue)
                .where(EmailQueue.entity_type == "onboarding_packets")
                .where(EmailQueue.entity_id == packet.id)
                .where(EmailQueue.subject == completion_subject)
            )
        ).scalars().all()
        assert len(same_subject) == 1
    finally:
        await cleanup_packet_storage(db_session, service, packet.id)
