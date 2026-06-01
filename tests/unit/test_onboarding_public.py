"""No-mock tests for the public (token-only) packet flow (build-order §3.2).

Drives the real ASGI routes with a bare access token + bearer session: the
e-mail gate (valid / wrong / token+IP lockout / expired session), packet-scoped
document access, lost-update 409s, the read-before-sign gate, abuse caps,
signature PNG validation, and the FULL happy path (verify → view → fill → sign
→ complete → in-session download URL → download proxies the signed PDF).

No mocks. Real templates, real PDFs, real signature PNG, real stamping. E-mail
side effects are asserted as ``EmailQueue`` rows + status, never a live send.
"""

import time
import uuid

import pytest

from src.onboarding import storage, tokens
from src.onboarding.models import OnboardingPacket
from src.onboarding.packet_service import PacketService

from ._onboarding_helpers import (
    cleanup_packet_storage,
    make_template,
    png_bytes,
    signature_field,
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


async def _make_packet(
    db,
    contact_id,
    *,
    field_definitions=None,
    requires_esign=False,
    created_by_id=None,
):
    """Create a real packet and return (service, packet, raw_access_token)."""
    template = await make_template(
        db,
        field_definitions=field_definitions or [text_field("full_name")],
        requires_esign=requires_esign,
    )
    service = PacketService(db)
    packet, raw = await service.create_packet(
        created_by_id=created_by_id,
        contact_id=contact_id,
        recipient_email=RECIPIENT,
        template_ids=[template.id],
    )
    await db.commit()
    return service, packet, raw


def _b64png() -> str:
    import base64

    return base64.b64encode(png_bytes()).decode("ascii")


# --------------------------------------------------------------------------
# Pre-gate vs post-gate visibility
# --------------------------------------------------------------------------


async def test_pre_gate_hides_documents(client, db_session, test_contact):
    """GET /public/{token} with no session returns counts only, no documents."""
    service, packet, raw = await _make_packet(db_session, test_contact.id)
    try:
        resp = await client.get(f"/api/onboarding/public/{raw}")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["requires_email_verification"] is True
        assert body["document_count"] == 1
        assert "documents" not in body  # pre-gate schema omits documents
    finally:
        await cleanup_packet_storage(db_session, service, packet.id)


async def test_unknown_token_404(client):
    """An unknown access token is a 404 (no enumeration)."""
    resp = await client.get(f"/api/onboarding/public/{tokens.mint_token()}")
    assert resp.status_code == 404


# --------------------------------------------------------------------------
# Verify gate: success / wrong email / lockout / generic result
# --------------------------------------------------------------------------


async def test_verify_success_mints_session(client, db_session, test_contact):
    """Correct e-mail returns success + a usable session token."""
    service, packet, raw = await _make_packet(db_session, test_contact.id)
    try:
        resp = await client.post(
            f"/api/onboarding/public/{raw}/verify", json={"email": RECIPIENT}
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["success"] is True
        assert body["session_token"]
        # The minted session is bound to this packet.
        session = tokens.verify_session(body["session_token"])
        assert session["packet_id"] == packet.id
    finally:
        await cleanup_packet_storage(db_session, service, packet.id)


async def test_verify_wrong_email_generic_failure(client, db_session, test_contact):
    """A wrong e-mail returns a generic failure (no session, no enumeration)."""
    service, packet, raw = await _make_packet(db_session, test_contact.id)
    try:
        resp = await client.post(
            f"/api/onboarding/public/{raw}/verify",
            json={"email": "attacker@evil.com"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False
        assert body["session_token"] is None
    finally:
        await cleanup_packet_storage(db_session, service, packet.id)


async def test_verify_lockout_after_five_failures(client, db_session, test_contact):
    """Six wrong attempts from one IP trip the per-(token,ip) lockout → 429."""
    service, packet, raw = await _make_packet(db_session, test_contact.id)
    try:
        # 5 wrong attempts arm the counter; the 6th is locked out.
        for _ in range(5):
            r = await client.post(
                f"/api/onboarding/public/{raw}/verify",
                json={"email": "nope@evil.com"},
            )
            assert r.status_code == 200 and r.json()["success"] is False
        locked = await client.post(
            f"/api/onboarding/public/{raw}/verify", json={"email": RECIPIENT}
        )
        assert locked.status_code == 429
    finally:
        await cleanup_packet_storage(db_session, service, packet.id)


# --------------------------------------------------------------------------
# Session enforcement + cross-packet isolation
# --------------------------------------------------------------------------


async def _session_headers(client, raw) -> dict:
    resp = await client.post(
        f"/api/onboarding/public/{raw}/verify", json={"email": RECIPIENT}
    )
    return {"X-Onboarding-Session": resp.json()["session_token"]}


async def test_pdf_requires_session_401(client, db_session, test_contact):
    """Fetching a document PDF without a session is a 401."""
    service, packet, raw = await _make_packet(db_session, test_contact.id)
    try:
        doc = (await service.load_documents(packet.id))[0]
        resp = await client.get(
            f"/api/onboarding/public/{raw}/documents/{doc.id}/pdf"
        )
        assert resp.status_code == 401
    finally:
        await cleanup_packet_storage(db_session, service, packet.id)


async def test_session_for_packet_a_cannot_read_packet_b(
    client, db_session, test_contact
):
    """A session minted for packet A must not read packet B's document."""
    svc_a, packet_a, raw_a = await _make_packet(db_session, test_contact.id)
    svc_b, packet_b, raw_b = await _make_packet(db_session, test_contact.id)
    try:
        headers_a = await _session_headers(client, raw_a)
        doc_b = (await svc_b.load_documents(packet_b.id))[0]
        # Use packet B's token in the URL but packet A's session header → 401.
        resp = await client.get(
            f"/api/onboarding/public/{raw_b}/documents/{doc_b.id}/pdf",
            headers=headers_a,
        )
        assert resp.status_code == 401
    finally:
        await cleanup_packet_storage(db_session, svc_a, packet_a.id)
        await cleanup_packet_storage(db_session, svc_b, packet_b.id)


async def test_pdf_view_sets_opened_and_records_view(
    client, db_session, test_contact
):
    """First PDF view streams bytes, sets opened, and records the view row."""
    service, packet, raw = await _make_packet(db_session, test_contact.id)
    try:
        headers = await _session_headers(client, raw)
        doc = (await service.load_documents(packet.id))[0]
        resp = await client.get(
            f"/api/onboarding/public/{raw}/documents/{doc.id}/pdf",
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert resp.headers["referrer-policy"] == "no-referrer"
        assert resp.content.startswith(b"%PDF")
        # opened state + view-ledger row recorded.
        await db_session.refresh(packet)
        assert packet.status == "opened"
        from src.onboarding.view_ledger import get_unviewed_packet_document_ids

        unviewed = await get_unviewed_packet_document_ids(
            db_session, packet_id=packet.id, token=raw
        )
        assert unviewed == []
    finally:
        await cleanup_packet_storage(db_session, service, packet.id)


# --------------------------------------------------------------------------
# PATCH / signature: lost-update 409 + validation
# --------------------------------------------------------------------------


async def test_patch_version_drift_409(client, db_session, test_contact):
    """PATCH with a stale base_version is a 409 (lost-update guard)."""
    service, packet, raw = await _make_packet(db_session, test_contact.id)
    try:
        headers = await _session_headers(client, raw)
        doc = (await service.load_documents(packet.id))[0]
        # First save bumps the version to 1.
        ok = await client.patch(
            f"/api/onboarding/public/{raw}/documents/{doc.id}",
            headers=headers,
            json={"field_values": {"full_name": "Acme"}, "base_version": 0},
        )
        assert ok.status_code == 200
        assert ok.json()["field_values_version"] == 1
        # Re-submitting against base_version 0 now conflicts.
        conflict = await client.patch(
            f"/api/onboarding/public/{raw}/documents/{doc.id}",
            headers=headers,
            json={"field_values": {"full_name": "Other"}, "base_version": 0},
        )
        assert conflict.status_code == 409
    finally:
        await cleanup_packet_storage(db_session, service, packet.id)


async def test_patch_overflow_value_rejected_422_not_truncated(
    client, db_session, test_contact
):
    """An over-cap text value is rejected (422), never silently truncated."""
    service, packet, raw = await _make_packet(db_session, test_contact.id)
    try:
        headers = await _session_headers(client, raw)
        doc = (await service.load_documents(packet.id))[0]
        too_long = "x" * (4 * 1024 + 1)  # MAX_TEXT_VALUE_BYTES + 1
        resp = await client.patch(
            f"/api/onboarding/public/{raw}/documents/{doc.id}",
            headers=headers,
            json={"field_values": {"full_name": too_long}, "base_version": 0},
        )
        assert resp.status_code == 422
        # And nothing was persisted (no truncated value).
        await db_session.refresh(doc)
        assert doc.field_values.get("full_name") in (None,)
    finally:
        await cleanup_packet_storage(db_session, service, packet.id)


async def test_patch_unknown_field_rejected_422(client, db_session, test_contact):
    """A field id not in the document's definitions is rejected (422)."""
    service, packet, raw = await _make_packet(db_session, test_contact.id)
    try:
        headers = await _session_headers(client, raw)
        doc = (await service.load_documents(packet.id))[0]
        resp = await client.patch(
            f"/api/onboarding/public/{raw}/documents/{doc.id}",
            headers=headers,
            json={"field_values": {"ssn": "secret"}, "base_version": 0},
        )
        assert resp.status_code == 422
    finally:
        await cleanup_packet_storage(db_session, service, packet.id)


async def test_signature_version_drift_409(client, db_session, test_contact):
    """POST /signature with a stale base_signature_version is a 409."""
    service, packet, raw = await _make_packet(
        db_session, test_contact.id, requires_esign=True,
        field_definitions=[text_field("full_name"), signature_field()],
    )
    try:
        headers = await _session_headers(client, raw)
        first = await client.post(
            f"/api/onboarding/public/{raw}/signature",
            headers=headers,
            json={"signature_png_base64": _b64png(), "base_signature_version": 0},
        )
        assert first.status_code == 200
        assert first.json()["signature_version"] == 1
        stale = await client.post(
            f"/api/onboarding/public/{raw}/signature",
            headers=headers,
            json={"signature_png_base64": _b64png(), "base_signature_version": 0},
        )
        assert stale.status_code == 409
    finally:
        await cleanup_packet_storage(db_session, service, packet.id)


async def test_signature_rejects_non_png(client, db_session, test_contact):
    """A non-PNG signature payload is rejected (422, PNG-magic gate)."""
    import base64

    service, packet, raw = await _make_packet(
        db_session, test_contact.id, requires_esign=True,
        field_definitions=[signature_field()],
    )
    try:
        headers = await _session_headers(client, raw)
        not_png = base64.b64encode(b"GIF89a not a png").decode("ascii")
        resp = await client.post(
            f"/api/onboarding/public/{raw}/signature",
            headers=headers,
            json={"signature_png_base64": not_png, "base_signature_version": 0},
        )
        assert resp.status_code == 422
    finally:
        await cleanup_packet_storage(db_session, service, packet.id)


# --------------------------------------------------------------------------
# Abuse caps — the body cap helper + signature decoder are pure (the ASGI
# client always sets Content-Length, so the 411/413 caps are unit-tested on
# the helper directly with crafted headers; §6).
# --------------------------------------------------------------------------


def _request_with_headers(headers: dict) -> "Request":
    """Build a minimal Starlette Request carrying the given headers."""
    from starlette.requests import Request

    raw = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    return Request({"type": "http", "method": "POST", "headers": raw})


def test_missing_content_length_is_411():
    """A mutation body with no Content-Length is rejected 411 pre-parse."""
    from fastapi import HTTPException

    from src.core.constants import HTTPStatus
    from src.onboarding.public_helpers import assert_body_within_caps

    with pytest.raises(HTTPException) as exc:
        assert_body_within_caps(_request_with_headers({}))
    assert exc.value.status_code == HTTPStatus.LENGTH_REQUIRED  # 411


def test_over_cap_content_length_is_413():
    """An over-cap Content-Length is rejected 413 pre-parse."""
    from fastapi import HTTPException

    from src.core.constants import HTTPStatus
    from src.onboarding.public_helpers import MAX_BODY_BYTES, assert_body_within_caps

    with pytest.raises(HTTPException) as exc:
        assert_body_within_caps(
            _request_with_headers({"content-length": str(MAX_BODY_BYTES + 1)})
        )
    assert exc.value.status_code == HTTPStatus.PAYLOAD_TOO_LARGE  # 413


def test_within_cap_content_length_passes():
    """A reasonable Content-Length passes the cap check (no raise)."""
    from src.onboarding.public_helpers import assert_body_within_caps

    assert_body_within_caps(_request_with_headers({"content-length": "100"}))


def test_signature_over_200kb_rejected():
    """A signature PNG above the 200 KB cap is rejected (422)."""
    import base64

    from fastapi import HTTPException

    from src.core.constants import HTTPStatus
    from src.onboarding.public_helpers import (
        MAX_SIGNATURE_BYTES,
        decode_signature_png,
    )

    big = png_bytes() + b"\x00" * (MAX_SIGNATURE_BYTES + 1)
    payload = base64.b64encode(big).decode("ascii")
    with pytest.raises(HTTPException) as exc:
        decode_signature_png(payload)
    assert exc.value.status_code == HTTPStatus.UNPROCESSABLE_ENTITY  # 422


def test_signature_valid_png_decodes():
    """A valid small PNG decodes to the original bytes (data: prefix tolerated)."""
    import base64

    from src.onboarding.public_helpers import decode_signature_png

    raw = png_bytes()
    payload = "data:image/png;base64," + base64.b64encode(raw).decode("ascii")
    assert decode_signature_png(payload) == raw


async def test_complete_requires_viewed_documents(client, db_session, test_contact):
    """/complete is blocked (422) until every document has been opened."""
    service, packet, raw = await _make_packet(db_session, test_contact.id)
    doc = (await service.load_documents(packet.id))[0]
    pdf_path = doc.pdf_path  # capture before the route rolls back the session
    headers = await _session_headers(client, raw)
    # Fill the required field but DON'T view the document.
    await client.patch(
        f"/api/onboarding/public/{raw}/documents/{doc.id}",
        headers=headers,
        json={"field_values": {"full_name": "Acme"}, "base_version": 0},
    )
    resp = await client.post(
        f"/api/onboarding/public/{raw}/complete", headers=headers
    )
    assert resp.status_code == 422  # read-before-sign gate
    # The read-before-sign rejection ends in a route-level db.rollback() on the
    # shared test session, so we clean up by the path captured above rather
    # than re-querying the (now disturbed) session.
    await storage.delete(pdf_path)


# --------------------------------------------------------------------------
# FULL happy path: verify → view → fill → sign → complete → download
# --------------------------------------------------------------------------


async def test_full_happy_path_complete_and_download(
    client, db_session, test_contact, test_user
):
    """End-to-end: complete returns a usable download_url that proxies the PDF."""
    service, packet, raw = await _make_packet(
        db_session,
        test_contact.id,
        requires_esign=True,
        created_by_id=test_user.id,
        field_definitions=[text_field("full_name"), signature_field()],
    )
    try:
        headers = await _session_headers(client, raw)
        doc = (await service.load_documents(packet.id))[0]

        # Fill the required text field.
        patch = await client.patch(
            f"/api/onboarding/public/{raw}/documents/{doc.id}",
            headers=headers,
            json={"field_values": {"full_name": "Jane Client"}, "base_version": 0},
        )
        assert patch.status_code == 200

        # Draw the signature.
        sig = await client.post(
            f"/api/onboarding/public/{raw}/signature",
            headers=headers,
            json={"signature_png_base64": _b64png(), "base_signature_version": 0},
        )
        assert sig.status_code == 200

        # Open (view) the document — satisfies read-before-sign.
        view = await client.get(
            f"/api/onboarding/public/{raw}/documents/{doc.id}/pdf", headers=headers
        )
        assert view.status_code == 200

        # Complete.
        done = await client.post(
            f"/api/onboarding/public/{raw}/complete", headers=headers
        )
        assert done.status_code == 200, done.text
        body = done.json()
        assert body["status"] == "completed"
        download_url = body["download_url"]
        assert download_url and download_url.startswith("/api/onboarding/download/")

        # The in-session download_url lands on a usable landing payload...
        landing = await client.get(download_url)
        assert landing.status_code == 200, landing.text
        assert landing.headers["cache-control"] == "no-store"
        docs = landing.json()["documents"]
        assert len(docs) == 1

        # ...and the per-document URL proxies the stamped PDF bytes.
        pdf_resp = await client.get(docs[0]["url"])
        assert pdf_resp.status_code == 200
        assert pdf_resp.headers["content-type"] == "application/pdf"
        assert pdf_resp.headers["cache-control"] == "no-store"
        assert pdf_resp.headers["referrer-policy"] == "no-referrer"
        assert pdf_resp.content.startswith(b"%PDF")

        # PII is scrubbed post-completion; completion queued exactly 2 rows.
        await db_session.refresh(packet)
        assert packet.status == "completed"
        assert packet.signer_signature_image is None
        from sqlalchemy import select

        from src.email.models import EmailQueue

        rows = (
            await db_session.execute(
                select(EmailQueue)
                .where(EmailQueue.entity_type == "onboarding_packets")
                .where(EmailQueue.entity_id == packet.id)
            )
        ).scalars().all()
        # One client link + one owner notice (both tagged to the packet).
        recipients = {r.to_email for r in rows}
        assert RECIPIENT in recipients
        assert test_user.email in recipients
        assert len(rows) == 2
    finally:
        await cleanup_packet_storage(db_session, service, packet.id)
