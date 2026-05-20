"""Stamp a drawn signature image onto a master service agreement PDF
and append a signing audit-trail page.

Inputs
------
* ``master_pdf``: raw bytes of the original PDF uploaded by the rep
  (persisted at ``proposals.master_contract_pdf_path``).
* ``signature_png``: raw PNG bytes of the drawn signature.
* ``coords``: optional ``{page, x, y, width, height}`` JSON pointing
  at the slot in ``master_pdf`` where the signature image should land
  (PDF points; origin = bottom-left). ``None`` triggers auto-detect
  to the last page bottom-right. A coords payload that's missing
  ``x/y/width/height`` (or has invalid values) falls back to the
  bottom-right auto-box on the *requested* ``page`` rather than the
  last page.
* ``signer_*`` + ``signed_at`` + ``proposal_number``: rendered into
  the appended audit page so a printed copy is self-contained.

Returns the composite PDF bytes. Caller uploads to R2 and persists
the key on the proposal row. Failures raise ``ValueError`` so the
service layer can log and skip without unwinding acceptance — the
drawn signature image + audit DB row alone are ESIGN-Act § 7001
compliant evidence.
"""

from __future__ import annotations

import hashlib
import io
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

logger = logging.getLogger(__name__)

# Auto-detect signature box: last page, bottom-right with a ~0.5"
# inset. Sized to fit a typical drawn name (3" wide x 1" tall).
_AUTO_INSET_PT = 36.0
_AUTO_WIDTH_PT = 216.0
_AUTO_HEIGHT_PT = 72.0


@dataclass(frozen=True)
class StampInputs:
    master_pdf: bytes
    signature_png: bytes
    coords: dict[str, Any] | None
    signer_name: str
    signer_email: str
    signer_ip: str | None
    signer_user_agent: str | None
    signed_at: datetime
    proposal_number: str
    date_coords: dict[str, Any] | None = None
    date_label: str | None = None


def stamp_master_with_signature(inputs: StampInputs) -> bytes:
    """Return the composite signed PDF (master + stamp + audit page)."""
    if not inputs.master_pdf:
        raise ValueError("master_pdf is empty")
    if not inputs.signature_png:
        raise ValueError("signature_png is empty")

    reader = PdfReader(io.BytesIO(inputs.master_pdf))
    if len(reader.pages) == 0:
        raise ValueError("master_pdf has zero pages")

    target_page_idx, box = _resolve_target_box(reader, inputs.coords)
    target_page = reader.pages[target_page_idx]
    page_width = float(target_page.mediabox.width)
    page_height = float(target_page.mediabox.height)

    overlays: dict[int, list[bytes]] = {}
    overlays.setdefault(target_page_idx, []).append(_build_signature_overlay(
        page_width=page_width,
        page_height=page_height,
        signature_png=inputs.signature_png,
        box=box,
    ))
    if inputs.date_coords and inputs.date_label:
        # Skip the date stamp entirely if date_coords are malformed —
        # otherwise the auto-box fallback puts the date on top of the
        # signature (both default to bottom-right of last page).
        date_resolved = _resolve_date_box(reader, inputs.date_coords)
        if date_resolved is not None:
            date_page_idx, date_box = date_resolved
            date_page = reader.pages[date_page_idx]
            overlays.setdefault(date_page_idx, []).append(_build_date_overlay(
                page_width=float(date_page.mediabox.width),
                page_height=float(date_page.mediabox.height),
                box=date_box,
                date_label=inputs.date_label,
            ))

    writer = PdfWriter()

    for idx, src_page in enumerate(reader.pages):
        for overlay_bytes in overlays.get(idx, []):
            stamp_reader = PdfReader(io.BytesIO(overlay_bytes))
            src_page.merge_page(stamp_reader.pages[0])
        writer.add_page(src_page)

    audit_bytes = _build_audit_page(inputs)
    audit_reader = PdfReader(io.BytesIO(audit_bytes))
    for audit_page in audit_reader.pages:
        writer.add_page(audit_page)

    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def _resolve_target_box(
    reader: PdfReader, coords: dict[str, Any] | None,
) -> tuple[int, tuple[float, float, float, float]]:
    page_count = len(reader.pages)
    if not coords:
        return _auto_box(reader, page_count - 1)

    try:
        page = int(coords.get("page", page_count - 1))
    except (TypeError, ValueError):
        page = page_count - 1
    page = max(0, min(page_count - 1, page))

    target_page = reader.pages[page]
    page_w = float(target_page.mediabox.width)
    page_h = float(target_page.mediabox.height)

    try:
        x = float(coords["x"])
        y = float(coords["y"])
        width = float(coords["width"])
        height = float(coords["height"])
    except (KeyError, TypeError, ValueError):
        logger.warning("Malformed signature coords %r; using auto-box", coords)
        return _auto_box(reader, page)

    if width <= 0 or height <= 0:
        logger.warning("Zero/negative signature dims %r; using auto-box", coords)
        return _auto_box(reader, page)

    # Clamp so a wildly out-of-bounds coords payload still produces a
    # usable signed PDF rather than a silently-cropped one.
    x = max(0.0, min(x, page_w - 1.0))
    y = max(0.0, min(y, page_h - 1.0))
    width = min(width, page_w - x)
    height = min(height, page_h - y)
    return page, (x, y, width, height)


def _resolve_date_box(
    reader: PdfReader, coords: dict[str, Any],
) -> tuple[int, tuple[float, float, float, float]] | None:
    """Resolve date stamp coords, or return None to skip the date stamp.

    Unlike the signature path, malformed date coords MUST NOT fall back
    to the auto-box — that auto-box overlaps the signature and emits a
    silently-corrupt PDF where the date sits on top of the signature.
    """
    page_count = len(reader.pages)
    try:
        page = int(coords.get("page", page_count - 1))
        x = float(coords["x"])
        y = float(coords["y"])
        width = float(coords["width"])
        height = float(coords["height"])
    except (KeyError, TypeError, ValueError):
        logger.warning("Malformed proposal date coords %r; skipping date stamp", coords)
        return None
    if width <= 0 or height <= 0:
        logger.warning("Zero/negative date stamp dims %r; skipping date stamp", coords)
        return None

    page = max(0, min(page_count - 1, page))
    target_page = reader.pages[page]
    page_w = float(target_page.mediabox.width)
    page_h = float(target_page.mediabox.height)
    x = max(0.0, min(x, page_w - 1.0))
    y = max(0.0, min(y, page_h - 1.0))
    width = min(width, page_w - x)
    height = min(height, page_h - y)
    return page, (x, y, width, height)


def _auto_box(
    reader: PdfReader, page_index: int,
) -> tuple[int, tuple[float, float, float, float]]:
    page = reader.pages[page_index]
    page_w = float(page.mediabox.width)
    width = min(_AUTO_WIDTH_PT, page_w - 2 * _AUTO_INSET_PT)
    height = _AUTO_HEIGHT_PT
    x = page_w - width - _AUTO_INSET_PT
    y = _AUTO_INSET_PT
    return page_index, (x, y, width, height)


def _build_signature_overlay(
    page_width: float,
    page_height: float,
    signature_png: bytes,
    box: tuple[float, float, float, float],
) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(page_width, page_height))
    x, y, w, h = box
    # mask='auto' honors PNG alpha so the canvas's transparent
    # background doesn't paint a white rectangle over master content.
    c.drawImage(
        ImageReader(io.BytesIO(signature_png)),
        x,
        y,
        width=w,
        height=h,
        preserveAspectRatio=True,
        anchor="sw",
        mask="auto",
    )
    c.save()
    return buf.getvalue()


def _build_date_overlay(
    page_width: float,
    page_height: float,
    box: tuple[float, float, float, float],
    date_label: str,
) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(page_width, page_height))
    x, y, w, h = box
    font_size = max(7.0, min(12.0, h * 0.62))
    c.setFont("Helvetica", font_size)
    c.setFillGray(0.0)
    text_width = c.stringWidth(date_label, "Helvetica", font_size)
    text_x = x + max(0.0, (w - text_width) / 2)
    text_y = y + max(0.0, (h - font_size) / 2)
    c.drawString(text_x, text_y, date_label)
    c.save()
    return buf.getvalue()


def _build_audit_page(inputs: StampInputs) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER)
    width, height = LETTER

    left = 54.0
    top = height - 72.0
    line_gap = 16.0

    c.setFont("Helvetica-Bold", 18)
    c.drawString(left, top, "Electronic Signature Certificate")
    c.setFont("Helvetica", 10)
    c.setFillGray(0.35)
    c.drawString(
        left,
        top - 22,
        "This page is automatically generated and forms part of the executed agreement.",
    )
    c.setFillGray(0)

    rows = [
        ("Proposal", inputs.proposal_number),
        ("Signed by", _safe(inputs.signer_name) or "—"),
        ("Email", _safe(inputs.signer_email) or "—"),
        ("Signed at", inputs.signed_at.strftime("%Y-%m-%d %H:%M:%S UTC")),
        ("IP address", _safe(inputs.signer_ip) or "—"),
    ]
    y = top - 60
    for label, value in rows:
        c.setFont("Helvetica-Bold", 11)
        c.drawString(left, y, label)
        c.setFont("Helvetica", 11)
        c.drawString(left + 110, y, value)
        y -= line_gap

    c.setFont("Helvetica-Bold", 11)
    c.drawString(left, y, "User agent")
    c.setFont("Helvetica", 9)
    # Helvetica 9pt averages ~5pt/char; ~90 chars fits the 7.5" column.
    for line in _wrap_text(_safe(inputs.signer_user_agent) or "—", 90):
        c.drawString(left + 110, y, line)
        y -= line_gap - 4
    y -= 6

    c.setFont("Helvetica-Bold", 11)
    c.drawString(left, y, "Document hash")
    c.setFont("Courier", 9)
    digest = hashlib.sha256(inputs.master_pdf).hexdigest()
    c.drawString(left + 110, y, digest[:64])
    y -= line_gap

    y -= 18
    c.setFont("Helvetica-Oblique", 9)
    c.setFillGray(0.45)
    c.drawString(
        left,
        y,
        "Acceptance and signature were captured electronically under the ESIGN Act",
    )
    c.drawString(
        left,
        y - 12,
        "(15 U.S.C. § 7001 et seq.) and applicable state Uniform Electronic Transactions Acts.",
    )

    c.showPage()
    c.save()
    return buf.getvalue()


def _safe(value: str | None) -> str:
    if value is None:
        return ""
    cleaned = "".join(ch for ch in value if ch == " " or ord(ch) >= 32)
    return cleaned[:1024]


def _wrap_text(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    out: list[str] = []
    remaining = text
    while remaining:
        out.append(remaining[:max_chars])
        remaining = remaining[max_chars:]
    return out
