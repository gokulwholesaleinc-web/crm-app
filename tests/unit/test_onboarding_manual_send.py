"""No-mock tests for the Phase-1 manual send + link recovery + filename fix.

Covers:
- ``POST /packets`` with ``send_email=True`` queues an invite (token committed
  BEFORE the queue) when the sender's Gmail is connected, and still returns the
  one-time ``access_url`` for the copy-link secondary path.
- ``send_email=True`` is refused 400 (Connect-Gmail) when Gmail is NOT
  connected — and NO packet/token is minted.
- ``send_email`` omitted → copy-only: a packet + ``access_url`` but no invite
  email (no Gmail required).
- ``POST /packets/{id}/resend`` is refused 400 when the owner's Gmail is down,
  and the access token is NOT rotated (the live link survives).
- ``POST /packets/{id}/regenerate-link`` rotates the token + returns the NEW raw
  ``access_url`` to copy (no email by default; emails on request).
- ``create_packet`` stores a kind-appropriate ``original_filename`` (``.pdf``
  only for esign).

Real SQLite + ASGI client. Gmail is exercised via real ``GmailConnection`` rows
+ the stubbed Gmail HTTP send (``gmail_connected_test_user``) — neither the
guard nor the queue is mocked.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from src.attachments.service import AttachmentService
from src.email.models import EmailQueue
from src.onboarding import tokens
from src.onboarding.completion_notices import INVITE_SUBJECT
from src.onboarding.models import OnboardingPacket, OnboardingTemplate
from src.onboarding.packet_service import PacketService, ensure_pdf_suffix

from ._onboarding_helpers import (
    cleanup_packet_storage,
    make_template,
    one_page_pdf,
)

pytestmark = pytest.mark.asyncio

RECIPIENT = "client@example.com"


async def _invite_count(db, packet_id: int) -> int:
    return (
        await db.execute(
            select(func.count())
            .select_from(EmailQueue)
            .where(EmailQueue.entity_type == "onboarding_packets")
            .where(EmailQueue.entity_id == packet_id)
            .where(EmailQueue.subject == INVITE_SUBJECT)
        )
    ).scalar_one()


async def _token_hash(db, packet_id: int) -> str:
    return (
        await db.execute(
            select(OnboardingPacket.token_hash).where(
                OnboardingPacket.id == packet_id
            )
        )
    ).scalar_one()


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


# --------------------------------------------------------------------------
# 1a — manual send via email
# --------------------------------------------------------------------------


async def test_manual_send_emails_invite_when_gmail_connected(
    client, db_session, test_contact, gmail_connected_test_user, auth_headers
):
    """send_email=True queues the invite + still returns access_url to copy."""
    template = await make_template(db_session)
    await db_session.commit()
    resp = await client.post(
        "/api/onboarding/packets",
        headers=auth_headers,
        json={
            "contact_id": test_contact.id,
            "recipient_email": RECIPIENT,
            "template_ids": [template.id],
            "send_email": True,
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    packet_id = body["id"]
    try:
        # The copy-link secondary action survives an email send.
        assert body["access_url"]
        # Exactly one invite was queued (after the token commit).
        assert await _invite_count(db_session, packet_id) == 1
    finally:
        await cleanup_packet_storage(db_session, PacketService(db_session), packet_id)


async def test_manual_send_refused_when_gmail_down_mints_nothing(
    client, db_session, test_contact, auth_headers
):
    """send_email=True with no Gmail → 400 Connect-Gmail and NO packet minted."""
    template = await make_template(db_session)
    await db_session.commit()
    resp = await client.post(
        "/api/onboarding/packets",
        headers=auth_headers,
        json={
            "contact_id": test_contact.id,
            "recipient_email": RECIPIENT,
            "template_ids": [template.id],
            "send_email": True,
        },
    )
    assert resp.status_code == 400, resp.text
    assert "Gmail" in resp.json()["detail"]
    # Pre-flight runs BEFORE minting — not a single packet/token was created.
    count = (
        await db_session.execute(
            select(func.count())
            .select_from(OnboardingPacket)
            .where(OnboardingPacket.contact_id == test_contact.id)
        )
    ).scalar_one()
    assert count == 0


async def test_manual_send_copy_only_does_not_email(
    client, db_session, test_contact, auth_headers
):
    """Omitting send_email mints + returns access_url but queues no invite."""
    template = await make_template(db_session)
    await db_session.commit()
    resp = await client.post(
        "/api/onboarding/packets",
        headers=auth_headers,
        json={
            "contact_id": test_contact.id,
            "recipient_email": RECIPIENT,
            "template_ids": [template.id],
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    packet_id = body["id"]
    try:
        assert body["access_url"]
        assert await _invite_count(db_session, packet_id) == 0
    finally:
        await cleanup_packet_storage(db_session, PacketService(db_session), packet_id)


# --------------------------------------------------------------------------
# 1b — resend invite hardening
# --------------------------------------------------------------------------


async def test_resend_refused_when_owner_gmail_down_does_not_rotate(
    client, db_session, test_contact, test_user, auth_headers
):
    """Owner's Gmail down → resend is 400 and the live token is NOT rotated."""
    service, packet, _ = await _make_packet(
        db_session, test_contact.id, test_user.id
    )
    try:
        before = await _token_hash(db_session, packet.id)
        resp = await client.post(
            f"/api/onboarding/packets/{packet.id}/resend", headers=auth_headers
        )
        assert resp.status_code == 400, resp.text
        assert "Gmail" in resp.json()["detail"]
        # The live link survives — the guard ran BEFORE the rotation.
        assert await _token_hash(db_session, packet.id) == before
    finally:
        await cleanup_packet_storage(db_session, service, packet.id)


async def test_resend_emails_when_owner_gmail_connected(
    client, db_session, test_contact, gmail_connected_test_user, auth_headers
):
    """Owner connected → resend rotates the token + queues a fresh invite."""
    service, packet, raw = await _make_packet(
        db_session, test_contact.id, gmail_connected_test_user.id
    )
    try:
        before = await _token_hash(db_session, packet.id)
        resp = await client.post(
            f"/api/onboarding/packets/{packet.id}/resend", headers=auth_headers
        )
        assert resp.status_code == 200, resp.text
        assert await _token_hash(db_session, packet.id) != before
        assert await _invite_count(db_session, packet.id) == 1
    finally:
        await cleanup_packet_storage(db_session, service, packet.id)


# --------------------------------------------------------------------------
# 1c — link recovery (regenerate & copy)
# --------------------------------------------------------------------------


async def test_regenerate_link_rotates_and_returns_new_url_without_email(
    client, db_session, test_contact, test_user, auth_headers
):
    """regenerate-link returns a NEW raw access_url, rotates the token, no email.

    No Gmail required — copying the link in-hand strands nobody.
    """
    service, packet, old_raw = await _make_packet(
        db_session, test_contact.id, test_user.id
    )
    try:
        resp = await client.post(
            f"/api/onboarding/packets/{packet.id}/regenerate-link",
            headers=auth_headers,
            json={},
        )
        assert resp.status_code == 200, resp.text
        access_url = resp.json()["access_url"]
        assert access_url
        # The new link carries a fresh token; the old one no longer matches.
        new_raw = access_url.rsplit("/", 1)[-1]
        assert new_raw != old_raw
        new_hash = await _token_hash(db_session, packet.id)
        assert tokens.verify_hash(new_raw, new_hash)
        assert not tokens.verify_hash(old_raw, new_hash)
        # Copy-only by default — no invite email queued.
        assert await _invite_count(db_session, packet.id) == 0
    finally:
        await cleanup_packet_storage(db_session, service, packet.id)


async def test_regenerate_link_emails_when_requested(
    client, db_session, test_contact, gmail_connected_test_user, auth_headers
):
    """send_email=True on regenerate also queues the invite (Gmail connected)."""
    service, packet, _ = await _make_packet(
        db_session, test_contact.id, gmail_connected_test_user.id
    )
    try:
        resp = await client.post(
            f"/api/onboarding/packets/{packet.id}/regenerate-link",
            headers=auth_headers,
            json={"send_email": True},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["access_url"]
        assert await _invite_count(db_session, packet.id) == 1
    finally:
        await cleanup_packet_storage(db_session, service, packet.id)


# --------------------------------------------------------------------------
# 1d — kind-appropriate filename (no bogus .pdf on form kinds)
# --------------------------------------------------------------------------


async def test_create_packet_filename_is_kind_appropriate(db_session, test_contact):
    """esign doc → ``{name}.pdf``; questionnaire doc → bare ``{name}`` (F2)."""
    esign = await make_template(db_session, name="Signing Agreement")
    questionnaire = OnboardingTemplate(
        name="Client Information",
        kind="questionnaire",
        field_definitions=[
            {"id": "q1", "kind": "short_text", "label": "Name", "required": True}
        ],
        requires_esign=False,
        is_active=True,
        pdf_path=None,
    )
    db_session.add(questionnaire)
    await db_session.flush()

    service = PacketService(db_session)
    packet, _ = await service.create_packet(
        created_by_id=test_contact.owner_id,
        contact_id=test_contact.id,
        recipient_email=RECIPIENT,
        template_ids=[esign.id, questionnaire.id],
    )
    try:
        docs = await service.load_documents(packet.id)
        by_kind = {d.kind: d.original_filename for d in docs}
        assert by_kind["esign_pdf"] == "Signing Agreement.pdf"
        assert by_kind["questionnaire"] == "Client Information"
    finally:
        await cleanup_packet_storage(db_session, service, packet.id)


def test_ensure_pdf_suffix_appends_only_when_missing():
    """The helper appends ``.pdf`` to a bare title and is idempotent."""
    assert ensure_pdf_suffix("Client Information") == "Client Information.pdf"
    assert ensure_pdf_suffix("Signing Agreement.pdf") == "Signing Agreement.pdf"
    # Case-insensitive on the existing extension (no double-suffix).
    assert ensure_pdf_suffix("Scan.PDF") == "Scan.PDF"


async def test_download_content_disposition_reappends_pdf_for_form_kind(
    client, db_session, test_contact, test_user
):
    """A questionnaire doc's bare title downloads with a ``.pdf`` filename (F2).

    Builds the real completed state (real attachment bytes + a minted download
    token) and hits the download route — proving ``ensure_pdf_suffix`` keeps the
    served filename valid even though the doc TITLE has no extension.
    """
    questionnaire = OnboardingTemplate(
        name="Client Information",
        kind="questionnaire",
        field_definitions=[
            {"id": "q1", "kind": "short_text", "label": "Name", "required": True}
        ],
        requires_esign=False,
        is_active=True,
        pdf_path=None,
    )
    db_session.add(questionnaire)
    await db_session.flush()

    service = PacketService(db_session)
    packet, _ = await service.create_packet(
        created_by_id=test_user.id,
        contact_id=test_contact.id,
        recipient_email=RECIPIENT,
        template_ids=[questionnaire.id],
    )
    doc = (await service.load_documents(packet.id))[0]
    assert doc.original_filename == "Client Information"  # no extension stored

    # Real completed artifact: a genuine PDF attachment + a minted download token.
    att = await AttachmentService(db_session).create_from_bytes(
        content=one_page_pdf(),
        original_filename=ensure_pdf_suffix(doc.original_filename),
        entity_type="contacts",
        entity_id=test_contact.id,
        category="onboarding",
        uploaded_by=None,
        mime_type="application/pdf",
    )
    doc.attachment_id = att.id
    raw_download = tokens.mint_token()
    packet.status = "completed"
    packet.download_token_hash = tokens.hash_token(raw_download)
    packet.download_token_expires_at = datetime.now(UTC) + timedelta(days=7)
    await db_session.commit()

    try:
        resp = await client.get(
            f"/api/onboarding/download/{raw_download}/documents/{doc.id}"
        )
        assert resp.status_code == 200, resp.text
        assert resp.headers["content-type"] == "application/pdf"
        # The served filename carries .pdf even though the title doesn't.
        assert 'filename="Client Information.pdf"' in resp.headers[
            "content-disposition"
        ]
    finally:
        await cleanup_packet_storage(db_session, service, packet.id)
