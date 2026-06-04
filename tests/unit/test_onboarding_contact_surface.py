"""No-mock tests for the Phase-3 contact onboarding surface (D5).

The single-packet detail (GET /packets/{id}) now carries the client-uploaded
files with their packet/doc/field correlation; the list endpoint omits them
(no N+1). Internal columns (token_hash / content_sha256) are never surfaced.

Real SQLite + ASGI client; the upload row + its Attachment are genuine rows.
"""

import pytest
from src.attachments.service import AttachmentService
from src.onboarding.models import OnboardingPacketUpload, OnboardingTemplate
from src.onboarding.packet_service import PacketService

from ._onboarding_helpers import cleanup_packet_storage, one_page_pdf

pytestmark = pytest.mark.asyncio

RECIPIENT = "client@example.com"


async def _packet_with_upload(db, contact_id, created_by_id, *, attach: bool = True):
    """An upload_request packet with one uploaded-file row.

    ``attach=True`` (default) backs it with a genuine Attachment; ``attach=False``
    leaves ``attachment_id`` NULL to model an orphaned upload (the FK is SET NULL
    when the underlying attachment is deleted).
    """
    template = OnboardingTemplate(
        name=f"Brand assets {'att' if attach else 'orphan'}",
        kind="upload_request",
        field_definitions=[
            {"id": "u_logo", "kind": "file_upload", "label": "Logo",
             "required": True, "maxFiles": 1, "maxMB": 10}
        ],
        requires_esign=False,
        is_active=True,
        pdf_path=None,
    )
    db.add(template)
    await db.flush()

    service = PacketService(db)
    packet, _ = await service.create_packet(
        created_by_id=created_by_id,
        contact_id=contact_id,
        recipient_email=RECIPIENT,
        template_ids=[template.id],
    )
    doc = (await service.load_documents(packet.id))[0]

    att = None
    if attach:
        att = await AttachmentService(db).create_from_bytes(
            content=one_page_pdf(),
            original_filename="logo.png",
            entity_type="contacts",
            entity_id=contact_id,
            category="onboarding",
            uploaded_by=None,
            mime_type="image/png",
        )
    db.add(
        OnboardingPacketUpload(
            packet_document_id=doc.id,
            field_id="u_logo",
            attachment_id=att.id if att else None,
            original_filename="logo.png",
            byte_size=2048,
            content_sha256="a" * 64,
            mime_type="image/png",
            sensitive=True,
            token_hash="b" * 64,
        )
    )
    await db.commit()
    return service, packet, doc, att


async def test_get_packet_includes_uploads(
    client, db_session, test_contact, test_user, auth_headers
):
    """GET /packets/{id} surfaces the upload with its doc/field correlation."""
    service, packet, doc, att = await _packet_with_upload(
        db_session, test_contact.id, test_user.id
    )
    try:
        resp = await client.get(
            f"/api/onboarding/packets/{packet.id}", headers=auth_headers
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert len(body["uploads"]) == 1
        up = body["uploads"][0]
        assert up["field_id"] == "u_logo"
        assert up["packet_document_id"] == doc.id
        assert up["attachment_id"] == att.id
        assert up["original_filename"] == "logo.png"
        assert up["sensitive"] is True
        # Internal columns are never exposed.
        assert "token_hash" not in up
        assert "content_sha256" not in up
    finally:
        await cleanup_packet_storage(db_session, service, packet.id)


async def test_get_packet_serializes_null_attachment_id(
    client, db_session, test_contact, test_user, auth_headers
):
    """An orphaned upload (attachment SET NULL on delete) serializes as null —
    the field is ``int | None`` and the whole FE download guard depends on it."""
    service, packet, _doc, att = await _packet_with_upload(
        db_session, test_contact.id, test_user.id, attach=False
    )
    assert att is None
    try:
        resp = await client.get(
            f"/api/onboarding/packets/{packet.id}", headers=auth_headers
        )
        assert resp.status_code == 200, resp.text
        uploads = resp.json()["uploads"]
        assert len(uploads) == 1
        assert uploads[0]["attachment_id"] is None
    finally:
        await cleanup_packet_storage(db_session, service, packet.id)


async def test_list_packets_omits_uploads(
    client, db_session, test_contact, test_user, auth_headers
):
    """The list endpoint leaves uploads empty (avoids an N+1 per packet)."""
    service, packet, _doc, _att = await _packet_with_upload(
        db_session, test_contact.id, test_user.id
    )
    try:
        resp = await client.get(
            f"/api/onboarding/packets?contact_id={test_contact.id}",
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        rows = resp.json()
        assert len(rows) == 1
        assert rows[0]["uploads"] == []
    finally:
        await cleanup_packet_storage(db_session, service, packet.id)
