"""No-mock tests for the completion download routes (build-order §3.3/§5.3).

The download MUST proxy the stamped PDF bytes (presign can't set headers) and
set ``Cache-Control: no-store`` + ``Referrer-Policy: no-referrer``. A revoked
packet (download_token_hash nulled) and an expired download token both 404.

We produce a REAL completed packet by running the public flow end-to-end
(verify → fill → sign → view → complete) so the download token + the contact
Attachment are genuine. Nothing is mocked.
"""

import base64
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from src.onboarding import tokens
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
    tokens._clear_all_throttle()
    yield
    tokens._clear_all_throttle()


def _b64png() -> str:
    return base64.b64encode(png_bytes()).decode("ascii")


async def _complete_packet_via_routes(client, db_session, contact_id, created_by_id):
    """Run the full public flow and return (service, packet, raw_download_token)."""
    template = await make_template(
        db_session,
        field_definitions=[text_field("full_name"), signature_field()],
        requires_esign=True,
    )
    service = PacketService(db_session)
    packet, raw = await service.create_packet(
        created_by_id=created_by_id,
        contact_id=contact_id,
        recipient_email=RECIPIENT,
        template_ids=[template.id],
    )
    await db_session.commit()

    verify = await client.post(
        f"/api/onboarding/public/{raw}/verify", json={"email": RECIPIENT}
    )
    headers = {"X-Onboarding-Session": verify.json()["session_token"]}
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
    # Phase-3: e-records consent is now a mandatory affirmative step before
    # /complete (it 422s otherwise).
    await client.post(
        f"/api/onboarding/public/{raw}/consent", headers=headers, json={}
    )
    await client.get(
        f"/api/onboarding/public/{raw}/documents/{doc.id}/pdf", headers=headers
    )
    done = await client.post(
        f"/api/onboarding/public/{raw}/complete", headers=headers
    )
    assert done.status_code == 200, done.text
    download_url = done.json()["download_url"]
    raw_download = download_url.rsplit("/", 1)[-1]
    return service, packet, raw_download


async def test_download_landing_lists_documents_no_store(
    client, db_session, test_contact, test_user
):
    """The landing route lists docs and sets Cache-Control: no-store."""
    service, packet, raw_download = await _complete_packet_via_routes(
        client, db_session, test_contact.id, test_user.id
    )
    try:
        resp = await client.get(f"/api/onboarding/download/{raw_download}")
        assert resp.status_code == 200, resp.text
        assert resp.headers["cache-control"] == "no-store"
        assert resp.headers["referrer-policy"] == "no-referrer"
        docs = resp.json()["documents"]
        assert len(docs) == 1
        assert docs[0]["url"].startswith(
            f"/api/onboarding/download/{raw_download}/documents/"
        )
    finally:
        await cleanup_packet_storage(db_session, service, packet.id)


async def test_download_document_proxies_bytes_with_security_headers(
    client, db_session, test_contact, test_user
):
    """The per-doc route PROXIES the stamped PDF and sets no-store/no-referrer."""
    service, packet, raw_download = await _complete_packet_via_routes(
        client, db_session, test_contact.id, test_user.id
    )
    try:
        landing = await client.get(f"/api/onboarding/download/{raw_download}")
        doc_url = landing.json()["documents"][0]["url"]
        resp = await client.get(doc_url)
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert resp.headers["cache-control"] == "no-store"
        assert resp.headers["referrer-policy"] == "no-referrer"
        assert "attachment" in resp.headers["content-disposition"]
        # Proxied bytes are a real, stamped PDF (the client's filled value is in it).
        assert resp.content.startswith(b"%PDF")
    finally:
        await cleanup_packet_storage(db_session, service, packet.id)


async def test_unknown_download_token_404(client):
    """An unknown download token is a 404."""
    resp = await client.get(f"/api/onboarding/download/{tokens.mint_token()}")
    assert resp.status_code == 404


async def test_revoked_packet_download_404(
    client, db_session, test_contact, test_user
):
    """Revoking the packet (nulling download_token_hash) makes download 404."""
    service, packet, raw_download = await _complete_packet_via_routes(
        client, db_session, test_contact.id, test_user.id
    )
    try:
        # Null the download token hash (what revoke does) directly on the row.
        await db_session.execute(
            OnboardingPacket.__table__.update()
            .where(OnboardingPacket.id == packet.id)
            .values(download_token_hash=None)
        )
        await db_session.commit()

        resp = await client.get(f"/api/onboarding/download/{raw_download}")
        assert resp.status_code == 404
    finally:
        await cleanup_packet_storage(db_session, service, packet.id)


async def test_expired_download_token_404(
    client, db_session, test_contact, test_user
):
    """A past download_token_expires_at makes the landing route 404."""
    service, packet, raw_download = await _complete_packet_via_routes(
        client, db_session, test_contact.id, test_user.id
    )
    try:
        # Mutate the live ORM object (kept aware) so the download route sees the
        # past expiry without forcing a naive reload from SQLite.
        fresh = (
            await db_session.execute(
                select(OnboardingPacket).where(OnboardingPacket.id == packet.id)
            )
        ).scalar_one()
        fresh.download_token_expires_at = datetime.now(UTC) - timedelta(days=1)
        await db_session.flush()

        resp = await client.get(f"/api/onboarding/download/{raw_download}")
        assert resp.status_code == 404
    finally:
        await cleanup_packet_storage(db_session, service, packet.id)
