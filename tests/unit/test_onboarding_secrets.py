"""No-mock tests for the sensitive-secret storage seam (v3 §A.4/§D.1, §F #1).

Owns the STORAGE side of F4 passwords (P2 owns the questionnaire handler that
produces the ciphertext): the ``onboarding_secret_values`` upsert in
``patch_document``, the owner/admin decrypt route, and scrub deleting secret
rows. Asserts a sensitive answer's plaintext is NEVER in ``field_values`` JSONB
nor the summary PDF, round-trips through the decrypt route, is gated owner/admin,
and is purged on scrub.

``ONBOARDING_FIELD_KEY`` is self-provisioned per test (monkeypatch) so the suite
never depends on the caller's env (CI has no key); the crypto module reads it
lazily on each call.
"""

from __future__ import annotations

import io

import pytest
from cryptography.fernet import Fernet
from pypdf import PdfReader
from sqlalchemy import func, select
from src.onboarding.models import (
    OnboardingPacketDocument,
    OnboardingSecretValue,
    OnboardingTemplate,
)
from src.onboarding.packet_service import PacketService

pytestmark = pytest.mark.asyncio

RECIPIENT = "client@example.com"
SENTINEL = "hunter2-SuperSecret-Sentinel-9931"


@pytest.fixture(autouse=True)
def _field_key(monkeypatch):
    """Provision a real Fernet key for ONBOARDING_FIELD_KEY (self-contained)."""
    monkeypatch.setenv("ONBOARDING_FIELD_KEY", Fernet.generate_key().decode())


def _q_fields() -> list[dict]:
    return [
        {"id": "name", "kind": "short_text", "label": "Name", "required": True},
        {
            "id": "pw",
            "kind": "short_text",
            "label": "Account Password",
            "required": True,
            "sensitive": True,
        },
    ]


async def _questionnaire_template(db) -> OnboardingTemplate:
    template = OnboardingTemplate(
        name="Credentials Form",
        field_definitions=_q_fields(),
        requires_esign=False,
        is_active=True,
        kind="questionnaire",
        pdf_path=None,
    )
    db.add(template)
    await db.flush()
    await db.refresh(template)
    return template


async def _make_q_packet(db, contact_id, *, created_by_id=None):
    template = await _questionnaire_template(db)
    service = PacketService(db)
    packet, raw = await service.create_packet(
        created_by_id=created_by_id,
        contact_id=contact_id,
        recipient_email=RECIPIENT,
        template_ids=[template.id],
    )
    await db.commit()
    return service, packet, raw


async def _session(client, raw) -> dict:
    resp = await client.post(
        f"/api/onboarding/public/{raw}/verify", json={"email": RECIPIENT}
    )
    return {"X-Onboarding-Session": resp.json()["session_token"]}


def _pdf_text(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    return "\n".join(p.extract_text() or "" for p in reader.pages)


# --------------------------------------------------------------------------
# PATCH stores ciphertext, never plaintext
# --------------------------------------------------------------------------


async def test_patch_stores_ciphertext_not_plaintext(client, db_session, test_contact):
    """A sensitive PATCH lands a secret row; the plaintext is NOT in field_values."""
    service, packet, raw = await _make_q_packet(db_session, test_contact.id)
    headers = await _session(client, raw)
    docs = await service.load_documents(packet.id)
    doc_id = docs[0].id
    resp = await client.patch(
        f"/api/onboarding/public/{raw}/documents/{doc_id}",
        headers=headers,
        json={"field_values": {"name": "Jane", "pw": SENTINEL}, "base_version": 0},
    )
    assert resp.status_code == 200, resp.text

    doc = (
        await db_session.execute(
            select(OnboardingPacketDocument).where(
                OnboardingPacketDocument.id == doc_id
            )
        )
    ).scalar_one()
    # Plaintext NEVER in the answer JSONB; the sensitive key is dropped/None.
    assert SENTINEL not in str(doc.field_values)
    assert doc.field_values.get("pw") is None
    assert doc.field_values.get("name") == "Jane"

    # The ciphertext is stored, and it does NOT contain the plaintext bytes.
    secret = (
        await db_session.execute(
            select(OnboardingSecretValue).where(
                OnboardingSecretValue.packet_document_id == doc_id
            )
        )
    ).scalar_one()
    assert secret.field_id == "pw"
    assert SENTINEL.encode() not in secret.ciphertext
    assert secret.key_version == 1


async def test_patch_upserts_secret_on_resave(client, db_session, test_contact):
    """Re-saving the sensitive field replaces (not duplicates) the secret row."""
    service, packet, raw = await _make_q_packet(db_session, test_contact.id)
    headers = await _session(client, raw)
    docs = await service.load_documents(packet.id)
    doc_id = docs[0].id
    url = f"/api/onboarding/public/{raw}/documents/{doc_id}"

    r1 = await client.patch(
        url,
        headers=headers,
        json={"field_values": {"name": "Jane", "pw": "first"}, "base_version": 0},
    )
    assert r1.status_code == 200, r1.text
    v1 = r1.json()["field_values_version"]
    r2 = await client.patch(
        url,
        headers=headers,
        json={"field_values": {"pw": "second"}, "base_version": v1},
    )
    assert r2.status_code == 200, r2.text

    count = (
        await db_session.execute(
            select(func.count())
            .select_from(OnboardingSecretValue)
            .where(OnboardingSecretValue.packet_document_id == doc_id)
        )
    ).scalar_one()
    assert count == 1  # upsert, not append


# --------------------------------------------------------------------------
# Decrypt route: round-trip + owner/admin gate
# --------------------------------------------------------------------------


async def _patch_secret(client, raw, headers, doc_id):
    return await client.patch(
        f"/api/onboarding/public/{raw}/documents/{doc_id}",
        headers=headers,
        json={"field_values": {"name": "Jane", "pw": SENTINEL}, "base_version": 0},
    )


async def test_decrypt_route_round_trips_for_owner(
    client, db_session, test_contact, auth_headers
):
    """The contact OWNER reads back the decrypted plaintext via the staff route."""
    # test_contact.owner_id == test_user (whom auth_headers authenticates).
    service, packet, raw = await _make_q_packet(db_session, test_contact.id)
    pub = await _session(client, raw)
    docs = await service.load_documents(packet.id)
    doc_id = docs[0].id
    assert (await _patch_secret(client, raw, pub, doc_id)).status_code == 200

    resp = await client.get(
        f"/api/onboarding/packets/{packet.id}/documents/{doc_id}/secrets",
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    values = {v["field_id"]: v["value"] for v in body["values"]}
    assert values["pw"] == SENTINEL  # the Fernet round-trip recovers the plaintext
    assert body["values"][0]["label"] == "Account Password"


async def test_decrypt_route_round_trips_for_admin(
    client, db_session, test_contact, admin_auth_headers
):
    """An admin (can_see_all) reads the decrypted plaintext for any contact."""
    service, packet, raw = await _make_q_packet(db_session, test_contact.id)
    pub = await _session(client, raw)
    docs = await service.load_documents(packet.id)
    doc_id = docs[0].id
    assert (await _patch_secret(client, raw, pub, doc_id)).status_code == 200

    resp = await client.get(
        f"/api/onboarding/packets/{packet.id}/documents/{doc_id}/secrets",
        headers=admin_auth_headers,
    )
    assert resp.status_code == 200, resp.text
    values = {v["field_id"]: v["value"] for v in resp.json()["values"]}
    assert values["pw"] == SENTINEL


async def test_decrypt_route_denied_for_non_owner_non_admin(
    client, db_session, test_contact, sales_rep_auth_headers
):
    """A scoped sales-rep who does NOT own the contact is refused (403)."""
    service, packet, raw = await _make_q_packet(db_session, test_contact.id)
    pub = await _session(client, raw)
    docs = await service.load_documents(packet.id)
    doc_id = docs[0].id
    assert (await _patch_secret(client, raw, pub, doc_id)).status_code == 200

    resp = await client.get(
        f"/api/onboarding/packets/{packet.id}/documents/{doc_id}/secrets",
        headers=sales_rep_auth_headers,
    )
    # The contact is owned by test_user, not the sales-rep → require_entity_access
    # already 403s (or the owner-or-admin gate does). Either way: forbidden.
    assert resp.status_code in (403, 404), resp.text


# --------------------------------------------------------------------------
# Sentinel ABSENT from the generated summary PDF
# --------------------------------------------------------------------------


async def test_sentinel_absent_from_summary_pdf(client, db_session, test_contact):
    """The sensitive plaintext is structurally absent from the summary PDF bytes."""
    from src.onboarding.kinds import get_handler

    service, packet, raw = await _make_q_packet(db_session, test_contact.id)
    headers = await _session(client, raw)
    docs = await service.load_documents(packet.id)
    doc_id = docs[0].id
    assert (await _patch_secret(client, raw, headers, doc_id)).status_code == 200

    doc = (
        await db_session.execute(
            select(OnboardingPacketDocument).where(
                OnboardingPacketDocument.id == doc_id
            )
        )
    ).scalar_one()
    out = await get_handler("questionnaire").produce_artifact(
        db_session, doc=doc, packet=packet, signature_png=None
    )
    assert out is not None and out.startswith(b"%PDF")
    text = _pdf_text(out)
    assert SENTINEL not in text  # the renderer reads field_values only
    assert SENTINEL.encode() not in out  # not even in the raw bytes


# --------------------------------------------------------------------------
# scrub deletes secret rows
# --------------------------------------------------------------------------


async def test_scrub_deletes_secret_rows(client, db_session, test_contact):
    """purge_pii → scrub_packet removes the onboarding_secret_values rows."""
    service, packet, raw = await _make_q_packet(db_session, test_contact.id)
    headers = await _session(client, raw)
    docs = await service.load_documents(packet.id)
    doc_id = docs[0].id
    assert (await _patch_secret(client, raw, headers, doc_id)).status_code == 200
    await db_session.commit()

    assert (
        await db_session.execute(
            select(func.count()).select_from(OnboardingSecretValue)
        )
    ).scalar_one() == 1

    fresh = await service.get_packet(packet.id)
    await service.purge_pii(fresh)
    await db_session.commit()

    assert (
        await db_session.execute(
            select(func.count()).select_from(OnboardingSecretValue)
        )
    ).scalar_one() == 0
