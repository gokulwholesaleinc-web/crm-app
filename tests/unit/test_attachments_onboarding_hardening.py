"""No-mock tests for the onboarding attachment hardening (v3 §D.4).

Covers the magic-byte sniff helper (unit), the hardened download headers
(``X-Content-Type-Options: nosniff`` + ``Content-Disposition: attachment``), and
the owner/admin gate on a ``category='onboarding_sensitive'`` attachment — a
shared-list / non-owner reader is refused, the owner + an admin are allowed.
No mocks: attachments are landed through the real ``AttachmentService`` (disk
fallback) and read through the real download route.
"""

from __future__ import annotations

import pytest
from src.attachments.service import (
    ONBOARDING_UPLOAD_EXTENSIONS,
    AttachmentService,
    sniff_magic_bytes,
)

from ._onboarding_helpers import one_page_pdf

pytestmark = pytest.mark.asyncio


# --------------------------------------------------------------------------
# Magic-byte sniff helper (pure unit)
# --------------------------------------------------------------------------


def test_sniff_accepts_real_pdf():
    assert sniff_magic_bytes(one_page_pdf(), "pdf") is True


def test_sniff_accepts_real_png():
    assert sniff_magic_bytes(b"\x89PNG\r\n\x1a\n\x00\x00", "png") is True


def test_sniff_accepts_jpeg():
    assert sniff_magic_bytes(b"\xff\xd8\xff\xe0\x00\x10JFIF", "jpg") is True


def test_sniff_accepts_gif():
    assert sniff_magic_bytes(b"GIF89a\x01\x00", "gif") is True


def test_sniff_accepts_webp():
    riff = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"VP8 "
    assert sniff_magic_bytes(riff, "webp") is True


def test_sniff_accepts_docx_zip():
    assert sniff_magic_bytes(b"PK\x03\x04rest-of-zip", "docx") is True


def test_sniff_rejects_svg_renamed_png():
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script/></svg>'
    assert sniff_magic_bytes(svg, "png") is False


def test_sniff_rejects_html_renamed_pdf():
    assert sniff_magic_bytes(b"<!doctype html><html></html>", "pdf") is False


def test_sniff_rejects_xml_prefix():
    assert sniff_magic_bytes(b"<?xml version='1.0'?><svg/>", "png") is False


def test_sniff_rejects_executable():
    assert sniff_magic_bytes(b"MZ\x90\x00", "png") is False
    assert sniff_magic_bytes(b"\x7fELF\x02", "pdf") is False


def test_sniff_rejects_empty():
    assert sniff_magic_bytes(b"", "pdf") is False


def test_sniff_rejects_mismatched_type():
    """Real PNG bytes claimed as a PDF are rejected (type/ext mismatch)."""
    assert sniff_magic_bytes(b"\x89PNG\r\n\x1a\n", "pdf") is False


# --------------------------------------------------------------------------
# F3 — polyglot rejection: a valid magic header followed by an embedded
# active-content payload in the first 2 KB window is rejected even though the
# leading bytes match the declared type.
# --------------------------------------------------------------------------


def test_sniff_rejects_gif_script_polyglot():
    """A GIF with a valid GIF89a header but an embedded <script> is rejected."""
    polyglot = b"GIF89a" + b"<script>alert(1)</script>" + b"\x00" * 64
    assert sniff_magic_bytes(polyglot, "gif") is False


def test_sniff_rejects_jpeg_svg_polyglot():
    """A JPEG with valid JFIF magic but an embedded <svg onload=...> is rejected."""
    polyglot = b"\xff\xd8\xff\xe0" + b'<svg onload="alert(1)">' + b"\x00" * 64
    assert sniff_magic_bytes(polyglot, "jpg") is False


def test_sniff_rejects_png_iframe_polyglot():
    """A PNG header followed by an <iframe> in the leading window is rejected."""
    polyglot = b"\x89PNG\r\n\x1a\n" + b'<iframe src="evil">' + b"\x00" * 64
    assert sniff_magic_bytes(polyglot, "png") is False


def test_sniff_rejects_php_polyglot():
    """A GIF header followed by a <?php tag is rejected (server-side exec)."""
    polyglot = b"GIF89a" + b"<?php system($_GET[0]); ?>" + b"\x00" * 64
    assert sniff_magic_bytes(polyglot, "gif") is False


def test_sniff_accepts_clean_gif_with_binary_body():
    """A clean GIF (valid header + real binary bytes, no tags) is accepted."""
    clean = b"GIF89a" + bytes(range(256)) * 4  # 1 KB of binary, no ASCII tags
    assert sniff_magic_bytes(clean, "gif") is True


def test_sniff_clean_png_still_accepted_after_polyglot_guard():
    """The polyglot window scan does not regress a legitimate PNG."""
    clean = b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * 4
    assert sniff_magic_bytes(clean, "png") is True


def test_onboarding_allow_list_is_the_confirmed_v1_set():
    """The onboarding upload allow-list is exactly the confirmed v1 set (§F #4)."""
    assert set(ONBOARDING_UPLOAD_EXTENSIONS) == {
        "pdf", "png", "jpg", "jpeg", "webp", "gif", "docx",
    }


# --------------------------------------------------------------------------
# Download headers + sensitive read-auth (through the real route)
# --------------------------------------------------------------------------


async def _sensitive_attachment(db, contact_id):
    return await AttachmentService(db).create_from_bytes(
        content=one_page_pdf(),
        original_filename="gov_id.pdf",
        entity_type="contacts",
        entity_id=contact_id,
        category="onboarding_sensitive",
        uploaded_by=None,
        mime_type="application/pdf",
    )


async def _onboarding_attachment(db, contact_id):
    return await AttachmentService(db).create_from_bytes(
        content=one_page_pdf(),
        original_filename="manifest.pdf",
        entity_type="contacts",
        entity_id=contact_id,
        category="onboarding",
        uploaded_by=None,
        mime_type="application/pdf",
    )


async def test_download_sets_nosniff_and_attachment_disposition(
    client, db_session, test_contact, auth_headers
):
    """A non-sensitive onboarding attachment download carries the hardened headers."""
    att = await _onboarding_attachment(db_session, test_contact.id)
    await db_session.commit()
    resp = await client.get(
        f"/api/attachments/{att.id}/download", headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers.get("x-content-type-options") == "nosniff"
    disposition = resp.headers.get("content-disposition", "")
    assert disposition.startswith("attachment")


async def test_sensitive_download_allowed_for_owner(
    client, db_session, test_contact, auth_headers
):
    """The contact OWNER (test_user via auth_headers) can read the sensitive file."""
    att = await _sensitive_attachment(db_session, test_contact.id)
    await db_session.commit()
    resp = await client.get(
        f"/api/attachments/{att.id}/download", headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers.get("x-content-type-options") == "nosniff"


async def test_sensitive_download_allowed_for_admin(
    client, db_session, test_contact, admin_auth_headers
):
    """An admin can read the sensitive file for any contact."""
    att = await _sensitive_attachment(db_session, test_contact.id)
    await db_session.commit()
    resp = await client.get(
        f"/api/attachments/{att.id}/download", headers=admin_auth_headers
    )
    assert resp.status_code == 200, resp.text


async def test_sensitive_download_denied_for_non_owner(
    client, db_session, test_contact, sales_rep_auth_headers
):
    """A scoped sales-rep who does NOT own the contact is refused the sensitive file."""
    att = await _sensitive_attachment(db_session, test_contact.id)
    await db_session.commit()
    resp = await client.get(
        f"/api/attachments/{att.id}/download", headers=sales_rep_auth_headers
    )
    assert resp.status_code in (403, 404), resp.text


# --------------------------------------------------------------------------
# F1 — sensitive attachment owner/admin gate on DELETE + list
# --------------------------------------------------------------------------


async def _attachment_exists(db, attachment_id: int) -> bool:
    from sqlalchemy import select
    from src.attachments.models import Attachment

    row = (
        await db.execute(select(Attachment.id).where(Attachment.id == attachment_id))
    ).scalar_one_or_none()
    return row is not None


async def test_sensitive_delete_denied_for_non_owner_keeps_file(
    client, db_session, test_contact, sales_rep_auth_headers
):
    """A non-owner non-admin DELETE of a sensitive attachment is refused, and the
    submitted gov-ID is NOT destroyed (a low-priv reader can't wipe it)."""
    att = await _sensitive_attachment(db_session, test_contact.id)
    await db_session.commit()
    resp = await client.delete(
        f"/api/attachments/{att.id}", headers=sales_rep_auth_headers
    )
    assert resp.status_code in (403, 404), resp.text
    # The attachment still exists — the gate fenced the destructive call.
    assert await _attachment_exists(db_session, att.id)


async def test_sensitive_delete_allowed_for_owner(
    client, db_session, test_contact, auth_headers
):
    """The contact OWNER can delete the sensitive attachment (204)."""
    att = await _sensitive_attachment(db_session, test_contact.id)
    await db_session.commit()
    resp = await client.delete(
        f"/api/attachments/{att.id}", headers=auth_headers
    )
    assert resp.status_code == 204, resp.text
    assert not await _attachment_exists(db_session, att.id)


async def test_sensitive_delete_allowed_for_admin(
    client, db_session, test_contact, admin_auth_headers
):
    """An admin can delete the sensitive attachment for any contact (204)."""
    att = await _sensitive_attachment(db_session, test_contact.id)
    await db_session.commit()
    resp = await client.delete(
        f"/api/attachments/{att.id}", headers=admin_auth_headers
    )
    assert resp.status_code == 204, resp.text
    assert not await _attachment_exists(db_session, att.id)


async def test_list_hides_sensitive_rows_from_non_owner(
    client, db_session, test_contact, auth_headers, sales_rep_auth_headers
):
    """The contact list omits onboarding_sensitive rows for a non-owner non-admin,
    while a non-sensitive onboarding row stays visible (metadata is PII)."""
    sensitive = await _sensitive_attachment(db_session, test_contact.id)
    plain = await _onboarding_attachment(db_session, test_contact.id)
    await db_session.commit()

    # The owner must be able to reach this contact's list for the contrast below;
    # the sales-rep is the non-owner whose view must hide the sensitive row.
    resp = await client.get(
        f"/api/attachments/contacts/{test_contact.id}",
        headers=sales_rep_auth_headers,
    )
    # If the sales-rep can't reach the contact at all, that's an even stronger
    # denial; only assert the hiding when the list is actually returned.
    if resp.status_code == 200:
        ids = {item["id"] for item in resp.json()["items"]}
        assert sensitive.id not in ids, "sensitive row must be hidden from non-owner"
        assert plain.id in ids, "non-sensitive onboarding row should remain visible"
    else:
        assert resp.status_code in (403, 404), resp.text


async def test_list_shows_sensitive_rows_to_owner(
    client, db_session, test_contact, auth_headers
):
    """The contact OWNER sees the onboarding_sensitive rows in the list."""
    sensitive = await _sensitive_attachment(db_session, test_contact.id)
    await db_session.commit()
    resp = await client.get(
        f"/api/attachments/contacts/{test_contact.id}", headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    ids = {item["id"] for item in resp.json()["items"]}
    assert sensitive.id in ids


async def test_list_shows_sensitive_rows_to_admin(
    client, db_session, test_contact, admin_auth_headers
):
    """An admin sees the onboarding_sensitive rows in any contact's list."""
    sensitive = await _sensitive_attachment(db_session, test_contact.id)
    await db_session.commit()
    resp = await client.get(
        f"/api/attachments/contacts/{test_contact.id}", headers=admin_auth_headers
    )
    assert resp.status_code == 200, resp.text
    ids = {item["id"] for item in resp.json()["items"]}
    assert sensitive.id in ids


# --------------------------------------------------------------------------
# PF3 — presigned object-storage URL forces an ATTACHMENT download
#
# The download route 307-redirects to an R2 presigned URL whenever object
# storage is configured; the nosniff+attachment headers only existed on the
# disk-fallback ``FileResponse`` branch (hence the rest of this file's
# "false confidence"). These exercise the presign builder directly: boto3's
# ``generate_presigned_url`` is a PURELY LOCAL signing operation (no network),
# so providing fake R2 credentials is enough to assert the override params are
# baked into the signed query string. No mocks.
# --------------------------------------------------------------------------


from urllib.parse import parse_qs, urlparse  # noqa: E402

from src.attachments import object_storage  # noqa: E402


@pytest.fixture
def fake_r2_env(monkeypatch):
    """Provision fake (but well-formed) R2 credentials so the presign signs
    locally without ever reaching the network."""
    monkeypatch.setenv("R2_ACCOUNT_ID", "acct-test")
    monkeypatch.setenv("R2_ACCESS_KEY_ID", "AKIAFAKEFAKEFAKE")
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "fake-secret-key-value-for-signing")
    monkeypatch.setenv("R2_BUCKET_NAME", "crm-app-test")


async def test_presigned_download_url_forces_attachment_disposition(fake_r2_env):
    """A presigned GET carries ``response-content-disposition`` (attachment +
    original filename) and ``response-content-type`` (octet-stream)."""
    url = await object_storage.get_download_url(
        "uploads/contacts/1/abc.pdf", filename="Government ID.pdf"
    )
    query = parse_qs(urlparse(url).query)
    assert "response-content-disposition" in query
    disposition = query["response-content-disposition"][0]
    assert disposition.startswith("attachment")
    assert "Government ID.pdf" in disposition
    assert query["response-content-type"][0] == "application/octet-stream"


async def test_presigned_download_url_sanitizes_filename(fake_r2_env):
    """CR/LF + double-quotes are stripped from the disposition filename so the
    signed header can't be injection-split or have its quoted-string closed."""
    url = await object_storage.get_download_url(
        "uploads/contacts/1/abc.pdf",
        filename='evil"\r\nSet-Cookie: x=1.pdf',
    )
    disposition = parse_qs(urlparse(url).query)["response-content-disposition"][0]
    assert "\r" not in disposition and "\n" not in disposition
    # The embedded quote + CR/LF are stripped, leaving a well-formed quoted-string.
    assert disposition == 'attachment; filename="evilSet-Cookie: x=1.pdf"'


async def test_presigned_download_url_omits_override_without_filename(fake_r2_env):
    """Back-compat: callers that pass no filename (contracts signed-PDF link) get
    a plain presign with no response-content-* override."""
    url = await object_storage.get_download_url("uploads/contacts/1/abc.pdf")
    query = parse_qs(urlparse(url).query)
    assert "response-content-disposition" not in query
    assert "response-content-type" not in query
