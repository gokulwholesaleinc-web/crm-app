"""No-mock tests for POST /public/{token}/documents/{doc_id}/viewed (P1, P0-4).

The kind-agnostic counterpart of the ``/pdf`` view side effect: a document that
has no PDF stream can still satisfy the read-before-sign gate by POSTing
``/viewed``. These drive the real ASGI route with a bare access token + the same
verify→``X-Onboarding-Session`` bearer session the ``/pdf`` tests use, asserting
the SAME idempotent ledger write + active→opened transition, plus the 409 status
guard and — the load-bearing P0-4 assertion — that the completion view-gate
(``get_unviewed_packet_document_ids``) is satisfiable for docs marked ONLY via
``/viewed`` (never streamed as PDFs).

No mocks. Real templates, real PDFs, real packets, real ledger rows.
"""

import pytest
from sqlalchemy import update
from src.onboarding import storage, tokens
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


async def _make_packet(db, contact_id, *, field_definitions=None):
    """Create a real single-doc packet; return (service, packet, raw_token)."""
    template = await make_template(
        db, field_definitions=field_definitions or [text_field("full_name")]
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
    """Create a real packet with THREE docs; return (service, packet, raw_token)."""
    templates = [
        await make_template(db, field_definitions=[text_field(f"f{i}")])
        for i in range(3)
    ]
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
# No-PDF /pdf guard (P0-5): a doc with pdf_path=None 404s on /pdf, while
# /viewed still works — the FE uses /viewed for such docs. We can't create a
# no-PDF doc in P1 (no questionnaire handler), so we null the copy directly to
# exercise the new get_public_document_pdf guard in isolation.
# --------------------------------------------------------------------------


async def test_pdf_404_when_doc_has_no_pdf(client, db_session, test_contact):
    """get_public_document_pdf 404s a doc with no PDF (the new no-stream guard)."""
    service, packet, raw = await _make_packet(db_session, test_contact.id)
    try:
        headers = await _session_headers(client, raw)
        doc = (await service.load_documents(packet.id))[0]
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

        # The same doc is still markable via /viewed (the kind-agnostic path).
        viewed = await client.post(
            f"/api/onboarding/public/{raw}/documents/{doc.id}/viewed",
            headers=headers,
        )
        assert viewed.status_code == 200, viewed.text
        assert viewed.json()["opened"] is True
    finally:
        await cleanup_packet_storage(db_session, service, packet.id)
