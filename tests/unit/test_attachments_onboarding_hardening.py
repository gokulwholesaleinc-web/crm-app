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
