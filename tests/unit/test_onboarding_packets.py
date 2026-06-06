"""No-mock tests for the staff packet lifecycle (build-order §3.1).

Exercises ``PacketService`` directly AND the authenticated staff routes via
the ASGI ``client`` fixture: create (+ one-time ``access_url``, frozen docs),
list/get access-checked (403 for a contact the caller can't see), revoke
(scrub + clear both token hashes + 409 when terminal), purge-pii. Real
templates + real PDFs; nothing mocked.
"""

import base64
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from src.contacts.models import Contact
from src.onboarding import tokens
from src.onboarding.packet_errors import PacketRaceError, PacketValidationError
from src.onboarding.packet_service import PacketService

from ._onboarding_helpers import (
    cleanup_packet_storage,
    make_questionnaire_template,
    make_template,
    png_bytes,
    questionnaire_field,
    signature_field,
    text_field,
)

pytestmark = pytest.mark.asyncio


# --------------------------------------------------------------------------
# Service-level: create / freeze / prefill
# --------------------------------------------------------------------------


async def test_create_packet_freezes_documents_and_returns_raw_token(
    db_session, test_contact
):
    """Should create one frozen doc per active template + return a raw token."""
    # t1 is a NON-e-sign questionnaire doc; t2 is a proper e-sign doc — a mixed
    # packet. (A bare text-only e-sign template is no longer send-ready under the
    # signature-aware H1 guard, so a generic "simple doc" is now a questionnaire.)
    t1 = await make_questionnaire_template(
        db_session, field_definitions=[questionnaire_field("full_name")]
    )
    t2 = await make_template(
        db_session,
        field_definitions=[text_field("ein"), signature_field()],
        requires_esign=True,
    )
    service = PacketService(db_session)

    packet, raw_token = await service.create_packet(
        created_by_id=test_contact.owner_id,
        contact_id=test_contact.id,
        recipient_email="client@example.com",
        template_ids=[t1.id, t2.id],
    )
    try:
        assert packet.status == "active"
        # token_hash persisted = sha256(raw); raw never stored as-is.
        assert packet.token_hash == tokens.hash_token(raw_token)
        assert tokens.verify_hash(raw_token, packet.token_hash)

        docs = await service.load_documents(packet.id)
        assert len(docs) == 2
        # display_order preserves the selection order.
        assert [d.display_order for d in docs] == [0, 1]
        # field_definitions are frozen copies (not template references).
        assert docs[0].field_definitions[0]["id"] == "full_name"
        # The e-sign doc carries the disclosure snapshot + version.
        esign_doc = next(d for d in docs if d.requires_esign)
        assert esign_doc.esign_disclosure_snapshot
        assert esign_doc.esign_disclosure_version
    finally:
        await cleanup_packet_storage(db_session, service, packet.id)


async def test_create_packet_seeds_prefill_from_contact(db_session, test_contact):
    """Should pre-populate a field carrying prefill='contact.name'."""
    template = await make_questionnaire_template(
        db_session,
        field_definitions=[questionnaire_field("name", prefill="contact.name")],
    )
    service = PacketService(db_session)
    packet, _ = await service.create_packet(
        created_by_id=None,
        contact_id=test_contact.id,
        recipient_email="client@example.com",
        template_ids=[template.id],
    )
    try:
        doc = (await service.load_documents(packet.id))[0]
        # test_contact is John Doe (conftest).
        assert doc.field_values["name"] == "John Doe"
    finally:
        await cleanup_packet_storage(db_session, service, packet.id)


async def test_create_packet_rejects_retired_template(db_session, test_contact):
    """Should refuse to build a packet from a retired template."""
    retired = await make_template(db_session, is_active=False)
    service = PacketService(db_session)
    from src.onboarding.packet_errors import PacketValidationError

    with pytest.raises(PacketValidationError):
        await service.create_packet(
            created_by_id=None,
            contact_id=test_contact.id,
            recipient_email="client@example.com",
            template_ids=[retired.id],
        )


# --------------------------------------------------------------------------
# Revoke / purge (service-level scrub correctness)
# --------------------------------------------------------------------------


async def _packet_with_values(db_session, contact_id):
    template = await make_questionnaire_template(
        db_session, field_definitions=[questionnaire_field("name", prefill="contact.name")]
    )
    service = PacketService(db_session)
    packet, raw = await service.create_packet(
        created_by_id=None,
        contact_id=contact_id,
        recipient_email="client@example.com",
        template_ids=[template.id],
    )
    packet.signer_signature_image = b"\x89PNG\r\n\x1a\nfake"
    await db_session.flush()
    return service, packet, raw


async def test_revoke_scrubs_and_clears_tokens(db_session, test_contact):
    """Should scrub values+signature, clear both token hashes, set revoked."""
    service, packet, raw = await _packet_with_values(db_session, test_contact.id)
    old_hash = packet.token_hash
    try:
        revoked = await service.revoke_packet(packet, revoked_by_id=7)
        assert revoked.status == "revoked"
        assert revoked.revoked_by_id == 7
        assert revoked.download_token_hash is None
        # token_hash replaced with an unusable dead placeholder (not the old one).
        assert revoked.token_hash != old_hash
        assert not tokens.verify_hash(raw, revoked.token_hash)
        # PII scrubbed.
        assert revoked.signer_signature_image is None
        for doc in await service.load_documents(packet.id):
            assert doc.field_values == {}
    finally:
        await cleanup_packet_storage(db_session, service, packet.id)


async def test_revoke_already_terminal_raises_409(db_session, test_contact):
    """Should raise PacketRaceError (→409) when revoking a terminal packet."""
    service, packet, _ = await _packet_with_values(db_session, test_contact.id)
    try:
        await service.revoke_packet(packet, revoked_by_id=1)
        with pytest.raises(PacketRaceError):
            await service.revoke_packet(packet, revoked_by_id=1)
    finally:
        await cleanup_packet_storage(db_session, service, packet.id)


async def test_expiry_sweep_scrubs_then_flips_status(db_session, test_contact):
    """SF1: the list-time expiry sweep SCRUBS PII and only THEN flips status to
    the terminal ``expired`` (status is the last mutation). The end state proves
    both halves ran in order: PII gone AND status terminal AND token invalidated.
    """
    service, packet, raw = await _packet_with_values(db_session, test_contact.id)
    # Plant a saved answer + signature so we can confirm the scrub actually ran.
    [doc] = await service.load_documents(packet.id)
    doc.field_values = {"name": "Jane Client"}
    old_hash = packet.token_hash
    # Force the access token into the past so the sweep treats it as expired.
    packet.token_expires_at = datetime.now(UTC) - timedelta(hours=1)
    await db_session.flush()

    try:
        # list_packets runs _sweep_packet on every row.
        await service.list_packets(test_contact.id)

        assert packet.status == "expired"          # terminal flip happened
        assert packet.token_hash != old_hash       # token invalidated (dead hash)
        assert not tokens.verify_hash(raw, packet.token_hash)
        # PII scrubbed BEFORE the flip — proves the scrub completed.
        assert packet.signer_signature_image is None
        for d in await service.load_documents(packet.id):
            assert d.field_values == {}
    finally:
        await cleanup_packet_storage(db_session, service, packet.id)


async def test_purge_pii_nulls_values_and_signature(db_session, test_contact):
    """Should null field_values + signature but leave status unchanged."""
    service, packet, _ = await _packet_with_values(db_session, test_contact.id)
    try:
        before_status = packet.status
        await service.purge_pii(packet)
        assert packet.status == before_status  # status unchanged (manual scrub)
        assert packet.signer_signature_image is None
        for doc in await service.load_documents(packet.id):
            assert doc.field_values == {}
    finally:
        await cleanup_packet_storage(db_session, service, packet.id)


# --------------------------------------------------------------------------
# Staff routes via the ASGI client (auth + access-control + access_url echo)
# --------------------------------------------------------------------------


async def test_create_packet_route_returns_access_url_once(
    client, db_session, test_contact, auth_headers
):
    """POST /packets returns access_url; GET never re-serves it."""
    template = await make_template(db_session)
    await db_session.commit()

    resp = await client.post(
        "/api/onboarding/packets",
        headers=auth_headers,
        json={
            "contact_id": test_contact.id,
            "recipient_email": "client@example.com",
            "template_ids": [template.id],
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["access_url"] and "/onboarding/" in body["access_url"]
    assert body["status"] == "active"
    assert body["document_count"] == 1
    # Recipient e-mail is masked, never echoed in full.
    assert body["recipient_email_masked"] == "c***@example.com"
    packet_id = body["id"]

    # GET single never re-serves the raw access_url.
    get_resp = await client.get(
        f"/api/onboarding/packets/{packet_id}", headers=auth_headers
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["access_url"] is None

    # The cross-request listing (which re-SELECTs the row — the path that used
    # to crash on a naive-reloaded token_expires_at) also omits the token.
    list_resp = await client.get(
        f"/api/onboarding/packets?contact_id={test_contact.id}", headers=auth_headers
    )
    assert list_resp.status_code == 200
    assert all(p["access_url"] is None for p in list_resp.json())


async def test_list_route_omits_access_url(
    client, db_session, test_contact, auth_headers
):
    """GET /packets lists the contact's packets, runs the sweep, omits tokens.

    Regression guard for the naive-vs-aware datetime fix (packet_service.py
    ``_ensure_aware``): we force ``token_expires_at`` to a NAIVE far-future
    value (exactly what a ``DateTime(timezone=True)`` column yields on SQLite
    / any naive-returning driver) so the list-time sweep's comparison runs on
    a naive value. It must NOT raise — the sweep leaves the unexpired packet
    untouched and the listing returns it without echoing any token."""
    template = await make_template(db_session)
    service = PacketService(db_session)
    packet, _ = await service.create_packet(
        created_by_id=test_contact.owner_id,
        contact_id=test_contact.id,
        recipient_email="client@example.com",
        template_ids=[template.id],
    )
    # Naive far-future expiry → the sweep must tolerate it (no TypeError).
    packet.token_expires_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(
        days=30
    )
    await db_session.commit()
    try:
        resp = await client.get(
            f"/api/onboarding/packets?contact_id={test_contact.id}",
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        rows = resp.json()
        assert len(rows) == 1
        assert rows[0]["id"] == packet.id
        assert rows[0]["status"] == "active"  # sweep left it unexpired
        assert all(p["access_url"] is None for p in rows)  # tokens never echoed
    finally:
        await cleanup_packet_storage(db_session, service, packet.id)


async def test_create_packet_missing_contact_returns_422(
    client, test_contact, auth_headers
):
    """POST /packets without contact_id is a 422 (schema)."""
    resp = await client.post(
        "/api/onboarding/packets",
        headers=auth_headers,
        json={"recipient_email": "client@example.com", "template_ids": [1]},
    )
    assert resp.status_code == 422


async def test_list_get_403_for_unscoped_contact(
    client, db_session, auth_headers, test_admin_user
):
    """A sales_rep can't list/get packets for a contact owned by someone else."""
    # A contact owned by a DIFFERENT user (the admin), not the sales-rep caller.
    other = Contact(
        first_name="Other",
        last_name="Owner",
        email=f"other-{uuid.uuid4().hex[:6]}@example.com",
        status="active",
        owner_id=test_admin_user.id,
        created_by_id=test_admin_user.id,
    )
    db_session.add(other)
    await db_session.commit()

    # List is access-checked on the contact → 403 for the sales-rep caller.
    list_resp = await client.get(
        f"/api/onboarding/packets?contact_id={other.id}", headers=auth_headers
    )
    assert list_resp.status_code == 403


async def test_revoke_route_scrubs_via_api(
    client, db_session, test_contact, auth_headers
):
    """POST /packets/{id}/revoke flips status + scrubs through the API."""
    template = await make_template(db_session)
    service = PacketService(db_session)
    packet, _ = await service.create_packet(
        created_by_id=test_contact.owner_id,
        contact_id=test_contact.id,
        recipient_email="client@example.com",
        template_ids=[template.id],
    )
    await db_session.commit()

    resp = await client.post(
        f"/api/onboarding/packets/{packet.id}/revoke", headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "revoked"

    # Second revoke is a 409 (already terminal).
    resp2 = await client.post(
        f"/api/onboarding/packets/{packet.id}/revoke", headers=auth_headers
    )
    assert resp2.status_code == 409
    await cleanup_packet_storage(db_session, service, packet.id)


# --------------------------------------------------------------------------
# e-sign ⇄ signature-field invariant (both directions) at packet creation
# --------------------------------------------------------------------------


async def test_create_packet_esign_override_without_signature_field_rejected(
    db_session, test_contact
):
    """requires_esign_override=True on a sig-less template is a 422.

    Forcing e-sign without a signature field would make the signer consent +
    draw a PNG the stamper draws nowhere → a consented PDF with no visible
    signature. Fail closed at create time instead.
    """
    template = await make_template(
        db_session,
        field_definitions=[text_field("full_name")],
        requires_esign=False,
    )
    service = PacketService(db_session)
    with pytest.raises(PacketValidationError):
        await service.create_packet(
            created_by_id=None,
            contact_id=test_contact.id,
            recipient_email="client@example.com",
            template_ids=[template.id],
            requires_esign_override=True,
        )


async def test_create_packet_signature_field_without_esign_rejected(
    db_session, test_contact
):
    """A signature field on a non-e-sign template is a 422.

    The fill page only shows the signature pad for e-sign docs, so completion
    (which requires a signature whenever a signature field exists) could never
    be satisfied → a permanently uncompletable packet. Reject at create time.
    """
    template = await make_template(
        db_session,
        field_definitions=[text_field("full_name"), signature_field()],
        requires_esign=False,
    )
    service = PacketService(db_session)
    with pytest.raises(PacketValidationError):
        await service.create_packet(
            created_by_id=None,
            contact_id=test_contact.id,
            recipient_email="client@example.com",
            template_ids=[template.id],
        )


async def test_create_packet_esign_with_signature_field_succeeds(
    db_session, test_contact
):
    """The consistent case (e-sign + a signature field) still creates fine."""
    template = await make_template(
        db_session,
        field_definitions=[text_field("full_name"), signature_field()],
        requires_esign=True,
    )
    service = PacketService(db_session)
    packet, _ = await service.create_packet(
        created_by_id=None,
        contact_id=test_contact.id,
        recipient_email="client@example.com",
        template_ids=[template.id],
    )
    try:
        doc = (await service.load_documents(packet.id))[0]
        assert doc.requires_esign is True
    finally:
        await cleanup_packet_storage(db_session, service, packet.id)


# --------------------------------------------------------------------------
# H1 (signature-aware e-sign integrity): an esign_pdf template with a PDF but
# ZERO signature fields must be un-sendable AND un-completable. Shipped today it
# is send-ready and COMPLETES into a flattened, attached, UNSIGNED "completed"
# PDF (no signature is ever collected) — a live legal/e-sign-integrity hole.
# --------------------------------------------------------------------------


async def test_create_packet_esign_pdf_without_signature_field_rejected(
    db_session, test_contact
):
    """H1 send guard: an esign_pdf + PDF + 0 signature fields is NOT send-ready.

    ``template_send_status`` is now signature-aware, so ``_load_active_templates``
    rejects the H1 shell at packet creation (it could only ever produce an
    unsigned 'signed' PDF). ``requires_esign`` is False here — exactly the state
    the library 'upload a PDF' path leaves a fresh e-sign template in, which never
    sets ``requires_esign`` and never requires a signature field.
    """
    template = await make_template(
        db_session,
        field_definitions=[text_field("full_name")],  # esign_pdf, 0 signature
        requires_esign=False,
    )
    assert template.kind == "esign_pdf" and template.pdf_path  # the H1 shape
    service = PacketService(db_session)
    with pytest.raises(PacketValidationError):
        await service.create_packet(
            created_by_id=None,
            contact_id=test_contact.id,
            recipient_email="client@example.com",
            template_ids=[template.id],
        )


async def test_completion_guard_blocks_esign_pdf_without_signature_field(
    db_session, test_contact
):
    """H1 completion guard: an in-flight esign_pdf packet whose doc carries a PDF
    but ZERO signature fields cannot complete — EVEN with a captured signature —
    because no signature field is bound to the document, so the stamper would
    flatten an unsigned PDF.

    The send guard now blocks creating such a packet, so we build the document
    directly to simulate one snapshotted BEFORE the guard shipped. A captured
    ``signer_signature_image`` is planted to prove it's the missing FIELD (not a
    missing PNG) that the new clause catches.
    """
    from src.onboarding.completion import _assert_signature_present
    from src.onboarding.models import OnboardingPacket, OnboardingPacketDocument

    service = PacketService(db_session)
    # A real PDF on storage (authentic pdf_path) but no signature field.
    template = await make_template(
        db_session,
        field_definitions=[text_field("full_name")],
        requires_esign=False,
    )
    raw_token = tokens.mint_token()
    packet = OnboardingPacket(
        contact_id=test_contact.id,
        recipient_email="client@example.com",
        token_hash=tokens.hash_token(raw_token),
        token_expires_at=datetime.now(UTC) + timedelta(days=30),
        status="in_progress",
        signer_signature_image=png_bytes(),  # a signature WAS drawn
    )
    db_session.add(packet)
    await db_session.flush()
    doc = OnboardingPacketDocument(
        packet_id=packet.id,
        display_order=0,
        source_template_id=template.id,
        original_filename=f"{template.name}.pdf",
        kind="esign_pdf",
        pdf_path=template.pdf_path,
        field_definitions=[text_field("full_name")],  # 0 signature fields
        field_values={},
        requires_esign=False,
    )
    db_session.add(doc)
    await db_session.flush()

    try:
        with pytest.raises(PacketValidationError):
            _assert_signature_present(packet, [doc])
    finally:
        await cleanup_packet_storage(db_session, service, packet.id)


async def test_retry_completion_refuses_h1_esign_without_signature_field(
    db_session, test_contact
):
    """H1 retry choke point: ``retry_completion`` skips Phase A (it drives Phase B
    directly), so the signature-field guard is enforced again inside
    ``_phase_b_stamp``. A completion_failed packet whose esign_pdf doc carries a
    PDF but NO signature field must be REFUSED (stays completion_failed, no
    attachment) rather than stamped into an unsigned 'completed' PDF — even though
    a signature PNG was captured. Simulates a packet snapshotted before the guard.
    """
    from src.onboarding.completion import retry_completion
    from src.onboarding.models import OnboardingPacket, OnboardingPacketDocument

    service = PacketService(db_session)
    template = await make_template(
        db_session,
        field_definitions=[text_field("full_name")],  # esign_pdf, 0 signature
        requires_esign=False,
    )
    packet = OnboardingPacket(
        contact_id=test_contact.id,
        recipient_email="client@example.com",
        token_hash=tokens.hash_token(tokens.mint_token()),
        token_expires_at=datetime.now(UTC) + timedelta(days=30),
        status="completion_failed",
        completing_since=datetime.now(UTC) - timedelta(hours=1),
        signer_signature_image=png_bytes(),  # a signature PNG WAS captured
    )
    db_session.add(packet)
    await db_session.flush()
    doc = OnboardingPacketDocument(
        packet_id=packet.id,
        display_order=0,
        source_template_id=template.id,
        original_filename=f"{template.name}.pdf",
        kind="esign_pdf",
        pdf_path=template.pdf_path,
        field_definitions=[text_field("full_name")],  # 0 signature fields
        field_values={"full_name": "Jane Client"},
        requires_esign=False,
    )
    db_session.add(doc)
    await db_session.flush()
    packet_id = packet.id  # retry_completion commits → expires the ORM packet

    try:
        result = await retry_completion(db_session, packet=packet)
        assert result["status"] == "completion_failed"
        # The unsigned PDF was never stamped/attached.
        refreshed_doc = (await service.load_documents(packet_id))[0]
        assert refreshed_doc.attachment_id is None
    finally:
        await cleanup_packet_storage(db_session, service, packet_id)


async def test_proper_esign_with_signature_sends_and_completes(
    client, db_session, test_contact
):
    """Regression: a proper signed e-sign (PDF + signature field, requires_esign)
    is still send-ready AND completes end-to-end through the public flow — the H1
    guards reject only the no-signature-field state, never the real ceremony.
    """
    tokens._clear_all_throttle()
    template = await make_template(
        db_session,
        field_definitions=[text_field("full_name"), signature_field()],
        requires_esign=True,
    )
    service = PacketService(db_session)
    # Send-ready: the signature-aware guard lets a proper e-sign create cleanly.
    packet, raw = await service.create_packet(
        created_by_id=test_contact.owner_id,
        contact_id=test_contact.id,
        recipient_email="client@example.com",
        template_ids=[template.id],
    )
    await db_session.commit()
    try:
        verify = await client.post(
            f"/api/onboarding/public/{raw}/verify",
            json={"email": "client@example.com"},
        )
        assert verify.status_code == 200, verify.text
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
            json={
                "signature_png_base64": base64.b64encode(png_bytes()).decode("ascii"),
                "base_signature_version": 0,
            },
        )
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
        assert done.json()["status"] == "completed"
    finally:
        await cleanup_packet_storage(db_session, service, packet.id)


# --------------------------------------------------------------------------
# Staff create: unrelated company/proposal links are access-checked
# --------------------------------------------------------------------------


async def test_create_packet_unscoped_company_403(
    client, db_session, test_contact, auth_headers, test_admin_user
):
    """A scoped caller can't attach a company owned by someone else.

    Without the company access check, the unrelated company's name would leak
    to the recipient (disclosure / prefill / public response) and create a
    wrong association. (test_contact is owned by the caller, so the contact
    check passes — only the company link is unscoped.)
    """
    from src.companies.models import Company

    other_company = Company(
        name="Unrelated Co",
        owner_id=test_admin_user.id,
        created_by_id=test_admin_user.id,
    )
    db_session.add(other_company)
    await db_session.commit()
    template = await make_template(db_session)
    await db_session.commit()

    resp = await client.post(
        "/api/onboarding/packets",
        headers=auth_headers,
        json={
            "contact_id": test_contact.id,
            "recipient_email": "client@example.com",
            "template_ids": [template.id],
            "company_id": other_company.id,
        },
    )
    assert resp.status_code == 403
