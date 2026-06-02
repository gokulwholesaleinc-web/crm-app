"""No-mock tests for the public e-consent step (§D).

Asserts that ``POST /consent`` sets ``consented_at`` per e-sign doc, that
``/complete`` 422s when consent hasn't been recorded (and succeeds after), and
that the belt-and-suspenders disclosure-version echo 409s on a mismatch. Uses
the real public routes + a real session; no mocks.
"""

import base64

import pytest
from src.onboarding import tokens
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
    tokens._clear_all_throttle()
    yield
    tokens._clear_all_throttle()


async def _make_esign_packet(db, contact_id, created_by_id=None):
    template = await make_template(
        db,
        field_definitions=[text_field("full_name"), signature_field()],
        requires_esign=True,
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


async def _session_headers(client, raw):
    resp = await client.post(
        f"/api/onboarding/public/{raw}/verify", json={"email": RECIPIENT}
    )
    return {"X-Onboarding-Session": resp.json()["session_token"]}


def _b64png():
    return base64.b64encode(png_bytes()).decode("ascii")


async def test_consent_sets_consented_at(client, db_session, test_contact):
    """POST /consent stamps consented_at on the e-sign doc."""
    service, packet, raw = await _make_esign_packet(db_session, test_contact.id)
    try:
        headers = await _session_headers(client, raw)
        resp = await client.post(
            f"/api/onboarding/public/{raw}/consent", headers=headers, json={}
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["documents_consented"] == 1

        doc = (await service.load_documents(packet.id))[0]
        await db_session.refresh(doc)
        assert doc.consented_at is not None
    finally:
        await cleanup_packet_storage(db_session, service, packet.id)


async def test_consent_is_idempotent(client, db_session, test_contact):
    """A second /consent reports 0 newly-consented docs (already consented)."""
    service, packet, raw = await _make_esign_packet(db_session, test_contact.id)
    try:
        headers = await _session_headers(client, raw)
        first = await client.post(
            f"/api/onboarding/public/{raw}/consent", headers=headers, json={}
        )
        assert first.json()["documents_consented"] == 1
        second = await client.post(
            f"/api/onboarding/public/{raw}/consent", headers=headers, json={}
        )
        assert second.status_code == 200
        assert second.json()["documents_consented"] == 0
    finally:
        await cleanup_packet_storage(db_session, service, packet.id)


async def test_complete_422_without_consent_then_succeeds(
    client, db_session, test_contact, test_user
):
    """/complete 422s when consent is missing; succeeds after /consent."""
    service, packet, raw = await _make_esign_packet(
        db_session, test_contact.id, created_by_id=test_user.id
    )
    try:
        headers = await _session_headers(client, raw)
        doc = (await service.load_documents(packet.id))[0]
        await client.patch(
            f"/api/onboarding/public/{raw}/documents/{doc.id}",
            headers=headers,
            json={"field_values": {"full_name": "Jane Client"}, "base_version": 0},
        )
        await client.post(
            f"/api/onboarding/public/{raw}/signature",
            headers=headers,
            json={"signature_png_base64": _b64png(), "base_signature_version": 0},
        )
        await client.get(
            f"/api/onboarding/public/{raw}/documents/{doc.id}/pdf", headers=headers
        )
        # Each real HTTP request commits via get_db; the test client shares one
        # session, so commit the filled state explicitly before the consent-gate
        # /complete (whose Phase-A rollback would otherwise discard it).
        await db_session.commit()

        # No consent yet → 422, status unchanged.
        blocked = await client.post(
            f"/api/onboarding/public/{raw}/complete", headers=headers
        )
        assert blocked.status_code == 422, blocked.text
        await db_session.refresh(packet)
        assert packet.status not in ("completing", "completed", "completion_failed")

        # Record consent, then /complete succeeds.
        consent = await client.post(
            f"/api/onboarding/public/{raw}/consent", headers=headers, json={}
        )
        assert consent.status_code == 200
        done = await client.post(
            f"/api/onboarding/public/{raw}/complete", headers=headers
        )
        assert done.status_code == 200, done.text
        assert done.json()["status"] == "completed"
    finally:
        await cleanup_packet_storage(db_session, service, packet.id)


async def test_consent_version_echo_mismatch_409(client, db_session, test_contact):
    """A wrong echoed disclosure_version is a 409 (saw-stale-text guard)."""
    service, packet, raw = await _make_esign_packet(db_session, test_contact.id)
    try:
        headers = await _session_headers(client, raw)
        resp = await client.post(
            f"/api/onboarding/public/{raw}/consent",
            headers=headers,
            json={"disclosure_version": "definitely-not-the-stored-version"},
        )
        assert resp.status_code == 409, resp.text
        # consented_at must NOT have been set on a rejected mismatch.
        doc = (await service.load_documents(packet.id))[0]
        await db_session.refresh(doc)
        assert doc.consented_at is None
    finally:
        await cleanup_packet_storage(db_session, service, packet.id)


async def test_consent_version_echo_match_ok(client, db_session, test_contact):
    """The correct echoed disclosure_version records consent."""
    service, packet, raw = await _make_esign_packet(db_session, test_contact.id)
    try:
        headers = await _session_headers(client, raw)
        doc = (await service.load_documents(packet.id))[0]
        version = doc.esign_disclosure_version
        assert version
        resp = await client.post(
            f"/api/onboarding/public/{raw}/consent",
            headers=headers,
            json={"disclosure_version": version},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["documents_consented"] == 1
    finally:
        await cleanup_packet_storage(db_session, service, packet.id)
