"""No-mock tests for the fill-time file-upload fence + scrub (v3 §D.3/§D.4).

Drives the real ``POST/DELETE /{token}/documents/{id}/files`` endpoints through
the ASGI client against a real ``upload_request`` packet: magic-byte rejection
of a disguised SVG/HTML, per-field maxFiles/maxMB + per-packet aggregate cap,
the upload-row fence, the FILE-FENCE no-duplicate-on-completion-retry property,
and that ``scrub`` deletes the upload Attachments + rows. No mocks — files are
real bytes landed through real ``onboarding.storage`` (disk fallback) +
``AttachmentService``.
"""

from __future__ import annotations

import contextlib
import io

import pytest
from sqlalchemy import func, select
from src.attachments.models import Attachment
from src.onboarding import storage
from src.onboarding import uploads as uploads_mod
from src.onboarding.models import (
    OnboardingPacketDocument,
    OnboardingPacketUpload,
    OnboardingTemplate,
)
from src.onboarding.packet_service import PacketService

from ._onboarding_helpers import one_page_pdf

pytestmark = pytest.mark.asyncio

RECIPIENT = "client@example.com"


def _upload_field(fid="gov_id", *, required=True, sensitive=False, **ov) -> dict:
    field = {
        "id": fid,
        "kind": "file_upload",
        "label": fid.replace("_", " ").title(),
        "required": required,
        "maxFiles": 2,
        "maxMB": 5,
        "sensitive": sensitive,
    }
    field.update(ov)
    return field


def _png(num_bytes: int = 64) -> bytes:
    """A real PNG header + filler (valid magic, arbitrary size)."""
    head = b"\x89PNG\r\n\x1a\n"
    return head + b"\x00" * max(num_bytes - len(head), 0)


async def _upload_template(db, fields: list[dict]) -> OnboardingTemplate:
    template = OnboardingTemplate(
        name="Upload Form",
        field_definitions=fields,
        requires_esign=False,
        is_active=True,
        kind="upload_request",
        pdf_path=None,  # no PDF for an upload kind
    )
    db.add(template)
    await db.flush()
    await db.refresh(template)
    return template


async def _make_upload_packet(db, contact_id, fields, *, created_by_id=None):
    template = await _upload_template(db, fields)
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


async def _doc_id(service, packet) -> int:
    docs = await service.load_documents(packet.id)
    return docs[0].id


async def _cleanup(db):
    """Best-effort: delete any stored attachment objects this test created."""
    rows = (await db.execute(select(Attachment.file_path))).scalars().all()
    for path in rows:
        with contextlib.suppress(Exception):
            await storage.delete(path)


# --------------------------------------------------------------------------
# Magic-byte rejection
# --------------------------------------------------------------------------


async def test_upload_rejects_svg_disguised_as_png(client, db_session, test_contact):
    """An SVG payload renamed .png is rejected by the magic-byte sniff (422)."""
    service, packet, raw = await _make_upload_packet(
        db_session, test_contact.id, [_upload_field()]
    )
    headers = await _session(client, raw)
    doc_id = await _doc_id(service, packet)
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    try:
        resp = await client.post(
            f"/api/onboarding/public/{raw}/documents/{doc_id}/files",
            headers=headers,
            data={"field_id": "gov_id"},
            files={"file": ("logo.png", io.BytesIO(svg), "image/png")},
        )
        assert resp.status_code == 422, resp.text
        # Nothing landed.
        count = (
            await db_session.execute(
                select(func.count()).select_from(OnboardingPacketUpload)
            )
        ).scalar_one()
        assert count == 0
    finally:
        await _cleanup(db_session)


async def test_upload_rejects_html_disguised_as_pdf(client, db_session, test_contact):
    """An HTML payload renamed .pdf is rejected (no %PDF magic) → 422."""
    service, packet, raw = await _make_upload_packet(
        db_session, test_contact.id, [_upload_field()]
    )
    headers = await _session(client, raw)
    doc_id = await _doc_id(service, packet)
    html = b"<!doctype html><html><body>hi</body></html>"
    try:
        resp = await client.post(
            f"/api/onboarding/public/{raw}/documents/{doc_id}/files",
            headers=headers,
            data={"field_id": "gov_id"},
            files={"file": ("statement.pdf", io.BytesIO(html), "application/pdf")},
        )
        assert resp.status_code == 422, resp.text
    finally:
        await _cleanup(db_session)


async def test_upload_accepts_real_pdf(client, db_session, test_contact):
    """A genuine PDF lands an Attachment + a fence row + appends the id."""
    service, packet, raw = await _make_upload_packet(
        db_session, test_contact.id, [_upload_field()]
    )
    headers = await _session(client, raw)
    doc_id = await _doc_id(service, packet)
    try:
        resp = await client.post(
            f"/api/onboarding/public/{raw}/documents/{doc_id}/files",
            headers=headers,
            data={"field_id": "gov_id"},
            files={"file": ("id.pdf", io.BytesIO(one_page_pdf()), "application/pdf")},
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["field_id"] == "gov_id"
        assert len(body["field_uploads"]) == 1

        rows = (
            await db_session.execute(select(OnboardingPacketUpload))
        ).scalars().all()
        assert len(rows) == 1
        assert rows[0].attachment_id is not None
        # The answer JSONB references the row id.
        doc = (
            await db_session.execute(
                select(OnboardingPacketDocument).where(
                    OnboardingPacketDocument.id == doc_id
                )
            )
        ).scalar_one()
        assert doc.field_values.get("gov_id") == [rows[0].id]
    finally:
        await _cleanup(db_session)


# --------------------------------------------------------------------------
# Caps: maxFiles, maxMB, per-packet aggregate
# --------------------------------------------------------------------------


async def test_max_files_enforced(client, db_session, test_contact):
    """A 3rd file on a maxFiles=2 field is rejected (422)."""
    service, packet, raw = await _make_upload_packet(
        db_session, test_contact.id, [_upload_field(maxFiles=2)]
    )
    headers = await _session(client, raw)
    doc_id = await _doc_id(service, packet)
    url = f"/api/onboarding/public/{raw}/documents/{doc_id}/files"
    try:
        for i in range(2):
            ok = await client.post(
                url,
                headers=headers,
                data={"field_id": "gov_id"},
                files={"file": (f"f{i}.png", io.BytesIO(_png()), "image/png")},
            )
            assert ok.status_code == 201, ok.text
        third = await client.post(
            url,
            headers=headers,
            data={"field_id": "gov_id"},
            files={"file": ("f3.png", io.BytesIO(_png()), "image/png")},
        )
        assert third.status_code == 422, third.text
    finally:
        await _cleanup(db_session)


async def test_max_mb_enforced(client, db_session, test_contact):
    """A file over the field's maxMB is rejected (422)."""
    service, packet, raw = await _make_upload_packet(
        db_session, test_contact.id, [_upload_field(maxMB=1)]
    )
    headers = await _session(client, raw)
    doc_id = await _doc_id(service, packet)
    big = _png(2 * 1024 * 1024)  # 2 MB > 1 MB cap
    try:
        resp = await client.post(
            f"/api/onboarding/public/{raw}/documents/{doc_id}/files",
            headers=headers,
            data={"field_id": "gov_id"},
            files={"file": ("big.png", io.BytesIO(big), "image/png")},
        )
        assert resp.status_code == 422, resp.text
    finally:
        await _cleanup(db_session)


async def test_per_packet_aggregate_cap_enforced(
    client, db_session, test_contact, monkeypatch
):
    """The per-packet aggregate byte cap rejects an upload that would exceed it."""
    # Shrink the cap so a small file trips it (avoids writing 500 MB in a test).
    monkeypatch.setattr(uploads_mod, "MAX_PACKET_UPLOAD_BYTES", 100)
    service, packet, raw = await _make_upload_packet(
        db_session, test_contact.id, [_upload_field(maxMB=5)]
    )
    headers = await _session(client, raw)
    doc_id = await _doc_id(service, packet)
    try:
        resp = await client.post(
            f"/api/onboarding/public/{raw}/documents/{doc_id}/files",
            headers=headers,
            data={"field_id": "gov_id"},
            files={"file": ("f.png", io.BytesIO(_png(200)), "image/png")},
        )
        assert resp.status_code == 422, resp.text
        assert "total upload limit" in resp.text.lower()
    finally:
        await _cleanup(db_session)


# --------------------------------------------------------------------------
# Sensitive flag → onboarding_sensitive category
# --------------------------------------------------------------------------


async def test_sensitive_field_lands_sensitive_category(
    client, db_session, test_contact
):
    """A sensitive=true field marks the row sensitive + the Attachment category."""
    service, packet, raw = await _make_upload_packet(
        db_session, test_contact.id, [_upload_field("ssn_doc", sensitive=True)]
    )
    headers = await _session(client, raw)
    doc_id = await _doc_id(service, packet)
    try:
        resp = await client.post(
            f"/api/onboarding/public/{raw}/documents/{doc_id}/files",
            headers=headers,
            data={"field_id": "ssn_doc"},
            files={"file": ("id.pdf", io.BytesIO(one_page_pdf()), "application/pdf")},
        )
        assert resp.status_code == 201, resp.text
        row = (
            await db_session.execute(select(OnboardingPacketUpload))
        ).scalar_one()
        assert row.sensitive is True
        att = (
            await db_session.execute(
                select(Attachment).where(Attachment.id == row.attachment_id)
            )
        ).scalar_one()
        assert att.category == "onboarding_sensitive"
    finally:
        await _cleanup(db_session)


# --------------------------------------------------------------------------
# DELETE removes the Attachment + row + answer id
# --------------------------------------------------------------------------


async def test_delete_upload_removes_everything(client, db_session, test_contact):
    """DELETE drops the Attachment, the fence row, and the answer id."""
    service, packet, raw = await _make_upload_packet(
        db_session, test_contact.id, [_upload_field()]
    )
    headers = await _session(client, raw)
    doc_id = await _doc_id(service, packet)
    url = f"/api/onboarding/public/{raw}/documents/{doc_id}/files"
    try:
        up = await client.post(
            url,
            headers=headers,
            data={"field_id": "gov_id"},
            files={"file": ("id.pdf", io.BytesIO(one_page_pdf()), "application/pdf")},
        )
        upload_id = up.json()["upload_id"]
        att_id = (
            await db_session.execute(
                select(OnboardingPacketUpload.attachment_id).where(
                    OnboardingPacketUpload.id == upload_id
                )
            )
        ).scalar_one()

        delete = await client.request(
            "DELETE", f"{url}/{upload_id}", headers=headers
        )
        assert delete.status_code == 200, delete.text
        assert delete.json()["field_uploads"] == []

        # Row + Attachment both gone.
        assert (
            await db_session.execute(
                select(func.count())
                .select_from(OnboardingPacketUpload)
                .where(OnboardingPacketUpload.id == upload_id)
            )
        ).scalar_one() == 0
        assert (
            await db_session.execute(
                select(func.count())
                .select_from(Attachment)
                .where(Attachment.id == att_id)
            )
        ).scalar_one() == 0
        doc = (
            await db_session.execute(
                select(OnboardingPacketDocument).where(
                    OnboardingPacketDocument.id == doc_id
                )
            )
        ).scalar_one()
        assert "gov_id" not in (doc.field_values or {})
    finally:
        await _cleanup(db_session)


# --------------------------------------------------------------------------
# scrub deletes upload Attachments + rows
# --------------------------------------------------------------------------


async def test_scrub_deletes_upload_attachments_and_rows(
    client, db_session, test_contact
):
    """purge_pii → scrub_packet removes the upload Attachments + fence rows."""
    service, packet, raw = await _make_upload_packet(
        db_session, test_contact.id, [_upload_field()]
    )
    headers = await _session(client, raw)
    doc_id = await _doc_id(service, packet)
    url = f"/api/onboarding/public/{raw}/documents/{doc_id}/files"
    try:
        up = await client.post(
            url,
            headers=headers,
            data={"field_id": "gov_id"},
            files={"file": ("id.pdf", io.BytesIO(one_page_pdf()), "application/pdf")},
        )
        assert up.status_code == 201
        await db_session.commit()

        # Reload the packet on the test session and scrub it.
        fresh = await service.get_packet(packet.id)
        await service.purge_pii(fresh)
        await db_session.commit()

        assert (
            await db_session.execute(
                select(func.count()).select_from(OnboardingPacketUpload)
            )
        ).scalar_one() == 0
        # The upload Attachment is deleted by delete_attachment.
        assert (
            await db_session.execute(
                select(func.count())
                .select_from(Attachment)
                .where(Attachment.category == "onboarding")
            )
        ).scalar_one() == 0
    finally:
        await _cleanup(db_session)


# --------------------------------------------------------------------------
# File-fence: a completion retry does NOT re-create uploaded files
# --------------------------------------------------------------------------


async def test_completion_retry_does_not_duplicate_uploads(
    client, db_session, test_contact, test_user
):
    """The fill-time fence: completion + a staff retry never re-create files.

    Files attach at FILL time and live in onboarding_packet_uploads, NOT behind
    the document's single attachment_id (which holds the manifest). Running
    completion then ``retry_completion`` must leave the upload-row count
    unchanged — the manifest is regenerated, the client files are not.
    """
    from src.onboarding import completion

    service, packet, raw = await _make_upload_packet(
        db_session, test_contact.id, [_upload_field()], created_by_id=test_user.id
    )
    headers = await _session(client, raw)
    doc_id = await _doc_id(service, packet)
    url = f"/api/onboarding/public/{raw}/documents/{doc_id}/files"
    try:
        # Upload one file + mark the doc viewed (completion gate).
        up = await client.post(
            url,
            headers=headers,
            data={"field_id": "gov_id"},
            files={"file": ("id.pdf", io.BytesIO(one_page_pdf()), "application/pdf")},
        )
        assert up.status_code == 201, up.text
        viewed = await client.post(
            f"/api/onboarding/public/{raw}/documents/{doc_id}/viewed",
            headers=headers,
        )
        assert viewed.status_code == 200, viewed.text

        before = (
            await db_session.execute(
                select(func.count()).select_from(OnboardingPacketUpload)
            )
        ).scalar_one()
        assert before == 1

        # Complete the packet via the public route.
        done = await client.post(
            f"/api/onboarding/public/{raw}/complete", headers=headers
        )
        assert done.status_code == 200, done.text
        assert done.json()["status"] == "completed"

        after_complete = (
            await db_session.execute(
                select(func.count()).select_from(OnboardingPacketUpload)
            )
        ).scalar_one()
        # Completion SCRUBS the packet (Phase C) → uploads are deleted exactly
        # once; the count never INCREASES (no duplication). Retry must be a
        # no-op on a completed packet.
        fresh = await service.get_packet(packet.id)
        retry = await completion.retry_completion(db_session, packet=fresh)
        assert retry["status"] == "completed"
        await db_session.commit()

        after_retry = (
            await db_session.execute(
                select(func.count()).select_from(OnboardingPacketUpload)
            )
        ).scalar_one()
        assert after_retry == after_complete  # retry never re-creates files
    finally:
        await _cleanup(db_session)


# --------------------------------------------------------------------------
# Completion gate: a required upload field with no files → 422 (P0-8)
# --------------------------------------------------------------------------


async def test_completion_422s_when_required_upload_missing(
    client, db_session, test_contact
):
    """A required file_upload with zero uploaded files blocks completion (422)."""
    service, packet, raw = await _make_upload_packet(
        db_session, test_contact.id, [_upload_field(required=True)]
    )
    headers = await _session(client, raw)
    doc_id = await _doc_id(service, packet)
    # Capture the id NOW: the 422 path inside /complete rolls back the shared
    # session, which expires the cached ``packet`` — a later ``packet.id`` read
    # would lazy-load (MissingGreenlet on the async session).
    packet_id = packet.id
    try:
        # View the doc (so the all-viewed gate passes) but upload nothing.
        viewed = await client.post(
            f"/api/onboarding/public/{raw}/documents/{doc_id}/viewed",
            headers=headers,
        )
        assert viewed.status_code == 200, viewed.text
        done = await client.post(
            f"/api/onboarding/public/{raw}/complete", headers=headers
        )
        assert done.status_code == 422, done.text
        # Status unchanged (no claim) — still writable. Read via a fresh scalar
        # SELECT against the captured id.
        from src.onboarding.models import OnboardingPacket

        status = (
            await db_session.execute(
                select(OnboardingPacket.status).where(
                    OnboardingPacket.id == packet_id
                )
            )
        ).scalar_one()
        assert status in ("active", "opened", "in_progress")
    finally:
        await _cleanup(db_session)


async def test_completion_attaches_one_manifest_to_upload_doc(
    client, db_session, test_contact
):
    """On completion the upload doc gets exactly one manifest attachment_id."""
    service, packet, raw = await _make_upload_packet(
        db_session, test_contact.id, [_upload_field(required=True)]
    )
    headers = await _session(client, raw)
    doc_id = await _doc_id(service, packet)
    url = f"/api/onboarding/public/{raw}/documents/{doc_id}/files"
    try:
        up = await client.post(
            url,
            headers=headers,
            data={"field_id": "gov_id"},
            files={"file": ("id.pdf", io.BytesIO(one_page_pdf()), "application/pdf")},
        )
        assert up.status_code == 201, up.text
        upload_att_id = (
            await db_session.execute(
                select(OnboardingPacketUpload.attachment_id)
            )
        ).scalar_one()
        viewed = await client.post(
            f"/api/onboarding/public/{raw}/documents/{doc_id}/viewed",
            headers=headers,
        )
        assert viewed.status_code == 200, viewed.text
        done = await client.post(
            f"/api/onboarding/public/{raw}/complete", headers=headers
        )
        assert done.status_code == 200 and done.json()["status"] == "completed"

        # The doc's own attachment_id (the manifest) is set and is DISTINCT from
        # the client file's attachment — the fence stays reserved for the
        # single manifest artifact.
        doc_att_id = (
            await db_session.execute(
                select(OnboardingPacketDocument.attachment_id).where(
                    OnboardingPacketDocument.id == doc_id
                )
            )
        ).scalar_one()
        assert doc_att_id is not None
        assert doc_att_id != upload_att_id
    finally:
        await _cleanup(db_session)
