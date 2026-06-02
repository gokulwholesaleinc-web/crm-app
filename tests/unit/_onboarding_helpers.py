"""Shared no-mock builders for the Phase-2 onboarding packet tests.

Builds REAL artifacts — a one-page reportlab PDF written through
``onboarding.storage`` (disk-fallback in the test env), real
``OnboardingTemplate`` / ``OnboardingPacket`` / ``OnboardingPacketDocument``
rows, and real signature PNG bytes — so create/copy/stamp/download paths run
end-to-end without a single mock. Imported by ``test_onboarding_*`` files.
"""

from __future__ import annotations

import contextlib
import io
import struct
import uuid
import zlib

from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas
from src.onboarding import storage
from src.onboarding.models import OnboardingTemplate


def one_page_pdf(text: str = "Onboarding form") -> bytes:
    """A real one-page PDF (no form fields) the stamper can overlay onto."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER)
    c.drawString(72, 720, text)
    c.showPage()
    c.save()
    return buf.getvalue()


def png_bytes() -> bytes:
    """A tiny valid 1x1 red PNG (real magic header) for signatures."""
    width = height = 1
    raw = b"\x00" + b"\xff\x00\x00"
    compressed = zlib.compress(raw)

    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return (
            struct.pack(">I", len(data))
            + body
            + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", compressed)
        + chunk(b"IEND", b"")
    )


def text_field(fid: str = "full_name", *, required: bool = True, **overrides) -> dict:
    """A non-signature text field definition (matches schemas.FieldDefinition)."""
    field = {
        "id": fid,
        "kind": "text",
        "label": fid.replace("_", " ").title(),
        "required": required,
        "prefill": None,
        "page": 1,
        "x": 72.0,
        "y": 600.0,
        "w": 300.0,
        "h": 24.0,
    }
    field.update(overrides)
    return field


def signature_field(fid: str = "client_sig", **overrides) -> dict:
    field = {
        "id": fid,
        "kind": "signature",
        "label": "Signature",
        "required": True,
        "prefill": None,
        "page": 1,
        "x": 72.0,
        "y": 200.0,
        "w": 220.0,
        "h": 60.0,
    }
    field.update(overrides)
    return field


async def make_template(
    db,
    *,
    name: str | None = None,
    field_definitions: list[dict] | None = None,
    requires_esign: bool = False,
    is_active: bool = True,
    pdf: bytes | None = None,
    owner_id: int | None = None,
) -> OnboardingTemplate:
    """Create a template with a REAL PDF written to storage and return it.

    The caller is responsible for deleting ``template.pdf_path`` if it cares
    about disk cleanup (the per-packet copy is a separate object).
    """
    if field_definitions is None:
        field_definitions = [text_field()]
    name = name or f"Template {uuid.uuid4().hex[:8]}"
    key = f"onboarding_templates/test/{uuid.uuid4().hex}.pdf"
    pdf_path = await storage.write(key, pdf or one_page_pdf(), "application/pdf")
    template = OnboardingTemplate(
        name=name,
        field_definitions=field_definitions,
        requires_esign=requires_esign,
        is_active=is_active,
        pdf_path=pdf_path,
        owner_id=owner_id,
    )
    db.add(template)
    await db.flush()
    await db.refresh(template)
    return template


async def cleanup_packet_storage(db, service, packet_id: int) -> None:
    """Delete the per-packet PDF copies a packet wrote (best-effort).

    Reads ``pdf_path`` via a scalar SELECT (not ORM attribute access) so it
    stays safe even when a preceding route did a ``db.rollback()`` that left
    ORM objects expired — accessing an expired attribute would otherwise
    trigger a sync lazy-load (``MissingGreenlet``) on the async session.
    """
    from sqlalchemy import select
    from src.attachments.models import Attachment
    from src.onboarding.models import OnboardingPacketDocument

    try:
        rows = await db.execute(
            select(
                OnboardingPacketDocument.pdf_path,
                OnboardingPacketDocument.attachment_id,
            ).where(OnboardingPacketDocument.packet_id == packet_id)
        )
        records = rows.all()
    except Exception:  # noqa: BLE001 — best-effort test cleanup
        return
    paths = [r[0] for r in records]
    # Also delete any completed-attachment files the doc landed in storage.
    att_ids = [r[1] for r in records if r[1] is not None]
    if att_ids:
        try:
            att_rows = await db.execute(
                select(Attachment.file_path).where(Attachment.id.in_(att_ids))
            )
            paths.extend(r[0] for r in att_rows.all())
        except Exception:  # noqa: BLE001 — best-effort test cleanup
            pass
    for pdf_path in paths:
        # best-effort test cleanup — a missing/again-deleted file is fine
        with contextlib.suppress(Exception):
            await storage.delete(pdf_path)
