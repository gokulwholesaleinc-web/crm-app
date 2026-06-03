"""No-mock tests for POST /public/{token}/documents/{doc_id}/viewed (P1, P0-4; F1).

The kind-agnostic counterpart of the ``/pdf`` view side effect: a NON-STREAM
document (questionnaire / upload_request) has no PDF stream and satisfies the
read-before-sign gate by POSTing ``/viewed``. These drive the real ASGI route
with a bare access token + the same verify→``X-Onboarding-Session`` bearer
session the ``/pdf`` tests use, asserting the idempotent ledger write +
active→opened transition, the 409 status guard, and — the load-bearing P0-4
assertion — that the completion view-gate (``get_unviewed_packet_document_ids``)
is satisfiable for docs marked ONLY via ``/viewed``.

F1 (read-before-sign bypass): an ``esign_pdf`` doc records its view ONLY via
``/pdf``, so ``/viewed`` MUST REFUSE it (400) — otherwise a client could mark a
signing doc viewed without ever loading the PDF, satisfying ``_assert_all_viewed``
and bypassing the signing gate. The positive-path tests therefore use an
``upload_request`` doc (records_view_via_stream=False, needs_pdf_copy=False → no
PDF), and the esign path asserts the 400 refusal.

No mocks. Real templates, real packets, real ledger rows.
"""

import uuid

import pytest
from sqlalchemy import update
from src.onboarding import storage, tokens
from src.onboarding.models import OnboardingTemplate
from src.onboarding.packet_service import PacketService
from src.onboarding.view_ledger import get_unviewed_packet_document_ids

from ._onboarding_helpers import (
    cleanup_packet_storage,
    make_template,
    text_field,
)

pytestmark = pytest.mark.asyncio

RECIPIENT = "client@example.com"


@pytest.fixture(autouse=True)
def _isolate_throttle():
    """The verify throttle is process-global — clear it around every test."""
    tokens._clear_all_throttle()
    yield
    tokens._clear_all_throttle()


def _upload_field(fid: str = "gov_id") -> dict:
    return {
        "id": fid,
        "kind": "file_upload",
        "label": fid.replace("_", " ").title(),
        "required": False,
        "maxFiles": 2,
        "maxMB": 5,
    }


async def _make_upload_template(db, fields=None) -> OnboardingTemplate:
    """An upload_request template — records_view_via_stream=False, no PDF copy."""
    # Unique name per call — a multi-doc packet builds several of these, and
    # uq_onboarding_templates_name (S1) forbids same-name rows.
    template = OnboardingTemplate(
        name=f"Upload Form {uuid.uuid4().hex[:8]}",
        field_definitions=fields or [_upload_field()],
        requires_esign=False,
        is_active=True,
        kind="upload_request",
        pdf_path=None,
    )
    db.add(template)
    await db.flush()
    await db.refresh(template)
    return template


async def _make_packet(db, contact_id):
    """Create a real single UPLOAD-doc packet (no-stream kind, F1-eligible)."""
    template = await _make_upload_template(db)
    service = PacketService(db)
    packet, raw = await service.create_packet(
        created_by_id=None,
        contact_id=contact_id,
        recipient_email=RECIPIENT,
        template_ids=[template.id],
    )
    await db.commit()
    return service, packet, raw


async def _make_esign_packet(db, contact_id):
    """Create a real single ESIGN-doc packet (records via /pdf → F1 refuses /viewed)."""
    template = await make_template(
        db, field_definitions=[text_field("full_name")]
    )
    service = PacketService(db)
    packet, raw = await service.create_packet(
        created_by_id=None,
        contact_id=contact_id,
        recipient_email=RECIPIENT,
        template_ids=[template.id],
    )
    await db.commit()
    return service, packet, raw


async def _make_multi_doc_packet(db, contact_id):
    """Create a real packet with THREE upload docs; return (service, packet, raw)."""
    templates = [await _make_upload_template(db) for _ in range(3)]
    service = PacketService(db)
    packet, raw = await service.create_packet(
        created_by_id=None,
        contact_id=contact_id,
        recipient_email=RECIPIENT,
        template_ids=[t.id for t in templates],
    )
    await db.commit()
    return service, packet, raw


async def _session_headers(client, raw) -> dict:
    resp = await client.post(
        f"/api/onboarding/public/{raw}/verify", json={"email": RECIPIENT}
    )
    return {"X-Onboarding-Session": resp.json()["session_token"]}


# --------------------------------------------------------------------------
# Session gate — mirrors the /pdf-without-session test (require_session → 401)
# --------------------------------------------------------------------------


async def test_viewed_requires_session_401(client, db_session, test_contact):
    """POST /viewed without a session is rejected (require_session, like /pdf)."""
    service, packet, raw = await _make_packet(db_session, test_contact.id)
    try:
        doc = (await service.load_documents(packet.id))[0]
        resp = await client.post(
            f"/api/onboarding/public/{raw}/documents/{doc.id}/viewed"
        )
        assert resp.status_code == 401
    finally:
        await cleanup_packet_storage(db_session, service, packet.id)


# --------------------------------------------------------------------------
# First view: 200 {viewed, opened} + active→opened + first_opened_at set
# --------------------------------------------------------------------------


async def test_first_viewed_opens_packet(client, db_session, test_contact):
    """First /viewed → 200 {viewed:true, opened:true}; packet active→opened."""
    service, packet, raw = await _make_packet(db_session, test_contact.id)
    try:
        # Sanity: a brand-new packet starts active with no first-open timestamp.
        await db_session.refresh(packet)
        assert packet.status == "active"
        assert packet.first_opened_at is None

        headers = await _session_headers(client, raw)
        doc = (await service.load_documents(packet.id))[0]
        resp = await client.post(
            f"/api/onboarding/public/{raw}/documents/{doc.id}/viewed",
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"viewed": True, "opened": True}

        # The first view transitions active→opened exactly like /pdf does.
        await db_session.refresh(packet)
        assert packet.status == "opened"
        assert packet.first_opened_at is not None
    finally:
        await cleanup_packet_storage(db_session, service, packet.id)


# --------------------------------------------------------------------------
# Idempotent: second POST on the same doc → 200 {opened:false}
# --------------------------------------------------------------------------


async def test_second_viewed_is_idempotent(client, db_session, test_contact):
    """A repeat /viewed on the same doc → 200 {viewed:true, opened:false}."""
    service, packet, raw = await _make_packet(db_session, test_contact.id)
    try:
        headers = await _session_headers(client, raw)
        doc = (await service.load_documents(packet.id))[0]
        url = f"/api/onboarding/public/{raw}/documents/{doc.id}/viewed"

        first = await client.post(url, headers=headers)
        assert first.status_code == 200
        assert first.json()["opened"] is True

        second = await client.post(url, headers=headers)
        assert second.status_code == 200, second.text
        # Idempotent: the ledger row already exists under this token, so the
        # second call did NOT re-fire the active→opened transition.
        assert second.json() == {"viewed": True, "opened": False}
    finally:
        await cleanup_packet_storage(db_session, service, packet.id)


# --------------------------------------------------------------------------
# Status guard — a completing/completed packet rejects /viewed with 409
# --------------------------------------------------------------------------


@pytest.mark.parametrize("terminal_status", ["completing", "completed"])
async def test_viewed_on_finalizing_packet_409(
    client, db_session, test_contact, terminal_status
):
    """/viewed on a completing/completed packet → 409 (the finalize guard)."""
    service, packet, raw = await _make_packet(db_session, test_contact.id)
    try:
        headers = await _session_headers(client, raw)
        doc = (await service.load_documents(packet.id))[0]
        # Flip the packet into a finalizing state. The route shares this
        # session and resolves the packet from the identity map, so we set the
        # ORM attribute directly (not a synchronize_session=False UPDATE that
        # would leave the cached instance stale) and commit so the route sees it.
        packet.status = terminal_status
        await db_session.commit()

        resp = await client.post(
            f"/api/onboarding/public/{raw}/documents/{doc.id}/viewed",
            headers=headers,
        )
        assert resp.status_code == 409, resp.text
    finally:
        await cleanup_packet_storage(db_session, service, packet.id)


# --------------------------------------------------------------------------
# THE P0-4 ASSERTION: /viewed alone satisfies the completion view-gate
# --------------------------------------------------------------------------


async def test_viewed_alone_satisfies_completion_gate(
    client, db_session, test_contact
):
    """Marking EVERY doc via /viewed (never /pdf) clears the read-before-sign
    gate — get_unviewed_packet_document_ids returns [] for a doc never streamed.

    This is the dissolution of P0-4: the completion gate is no longer welded to
    the /pdf stream side effect, so a kind with no PDF can still be opened.
    """
    service, packet, raw = await _make_multi_doc_packet(db_session, test_contact.id)
    try:
        headers = await _session_headers(client, raw)
        docs = await service.load_documents(packet.id)
        assert len(docs) == 3

        # Before any view, the whole packet is unviewed.
        unviewed = await get_unviewed_packet_document_ids(
            db_session, packet_id=packet.id, token=raw
        )
        assert set(unviewed) == {d.id for d in docs}

        # Mark every doc via /viewed ONLY — never hit /pdf.
        for doc in docs:
            resp = await client.post(
                f"/api/onboarding/public/{raw}/documents/{doc.id}/viewed",
                headers=headers,
            )
            assert resp.status_code == 200, resp.text

        # The completion gate is satisfied for docs that were never streamed.
        unviewed = await get_unviewed_packet_document_ids(
            db_session, packet_id=packet.id, token=raw
        )
        assert unviewed == []
    finally:
        await cleanup_packet_storage(db_session, service, packet.id)


# --------------------------------------------------------------------------
# No-PDF /pdf guard (P0-5): an esign doc whose PDF copy is missing 404s on
# /pdf (the get_public_document_pdf no-stream guard), rather than 503-ing on a
# storage miss. Exercised on an ESIGN doc (records_view_via_stream=True) by
# nulling its copied pdf_path — the scenario the guard actually protects.
# --------------------------------------------------------------------------


async def test_pdf_404_when_esign_doc_has_no_pdf(client, db_session, test_contact):
    """get_public_document_pdf 404s an esign doc whose pdf_path is None."""
    service, packet, raw = await _make_esign_packet(db_session, test_contact.id)
    try:
        headers = await _session_headers(client, raw)
        doc = (await service.load_documents(packet.id))[0]
        assert doc.kind == "esign_pdf"
        # Free the storage object, then null the doc's pdf_path so the route's
        # no-PDF branch (not a storage 503) is what fires.
        if doc.pdf_path:
            await storage.delete(doc.pdf_path)
        from src.onboarding.models import OnboardingPacketDocument

        await db_session.execute(
            update(OnboardingPacketDocument)
            .where(OnboardingPacketDocument.id == doc.id)
            .values(pdf_path=None)
            .execution_options(synchronize_session=False)
        )
        await db_session.commit()

        resp = await client.get(
            f"/api/onboarding/public/{raw}/documents/{doc.id}/pdf", headers=headers
        )
        assert resp.status_code == 404, resp.text
    finally:
        await cleanup_packet_storage(db_session, service, packet.id)


async def test_viewed_succeeds_on_no_pdf_upload_doc(client, db_session, test_contact):
    """A no-PDF upload_request doc is markable via /viewed (the FE path for it)."""
    service, packet, raw = await _make_packet(db_session, test_contact.id)
    try:
        headers = await _session_headers(client, raw)
        doc = (await service.load_documents(packet.id))[0]
        # An upload_request doc natively carries pdf_path=None (no PDF copy).
        assert doc.pdf_path is None
        viewed = await client.post(
            f"/api/onboarding/public/{raw}/documents/{doc.id}/viewed",
            headers=headers,
        )
        assert viewed.status_code == 200, viewed.text
        assert viewed.json()["opened"] is True
    finally:
        await cleanup_packet_storage(db_session, service, packet.id)


# --------------------------------------------------------------------------
# F1 (read-before-sign bypass): /viewed REFUSES an esign doc (records via /pdf)
# --------------------------------------------------------------------------


async def test_viewed_refuses_esign_doc_400(client, db_session, test_contact):
    """POST /viewed on an esign_pdf doc → 400 (it records via /pdf only, F1).

    Without this, a client could mark a signing doc viewed without ever loading
    the PDF, satisfying ``_assert_all_viewed`` and bypassing the read-before-sign
    gate. The esign view must come from the /pdf byte stream.
    """
    service, packet, raw = await _make_esign_packet(db_session, test_contact.id)
    try:
        headers = await _session_headers(client, raw)
        doc = (await service.load_documents(packet.id))[0]
        assert doc.kind == "esign_pdf"
        resp = await client.post(
            f"/api/onboarding/public/{raw}/documents/{doc.id}/viewed",
            headers=headers,
        )
        assert resp.status_code == 400, resp.text

        # The refusal wrote NO ledger row — the esign doc is still unviewed, so
        # the read-before-sign gate is NOT bypassed.
        unviewed = await get_unviewed_packet_document_ids(
            db_session, packet_id=packet.id, token=raw
        )
        assert doc.id in unviewed
    finally:
        await cleanup_packet_storage(db_session, service, packet.id)
