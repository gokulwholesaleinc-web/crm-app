"""Stamp per-field values onto an onboarding template PDF and flatten it.

Phase 1 of the Client Onboarding feature. Given the raw bytes of a
template PDF plus a list of resolved field definitions (and optionally a
signature PNG), draw each field's value into its box and return a
flattened PDF — one with no interactive AcroForm so the result is a
static, archival document.

Field shape (one ``dict`` per field, as stored in
``onboarding_templates.field_definitions`` + a resolved ``value``)::

    {id, kind, label, description?, required, prefill, value?,
     page (1-indexed), x, y, w, h}   # x/y/w/h in PDF points, origin bottom-left

``kind`` is one of ``signature | date | text | address``. Coordinates
use the same convention as the proposals stamper: bottom-left origin,
PDF points, so no y-flip is needed at stamp time (reportlab's canvas
origin is also bottom-left). Page numbers are 1-indexed in storage and
translated to 0-indexed here, mirroring ``service._coords_for_stamper``.

The signature overlay builder is reused from the proposals stamper to
stay DRY; text/date/address share a new single/multi-line text overlay.

This module exposes a SYNCHRONOUS core (``stamp_document``) — the test
hook. Async callers wrap it in ``asyncio.to_thread`` in Phase 2.

Failures raise ``ValueError`` (fail closed): a bad date, text that
overflows its box, or a signature field without a PNG all raise rather
than emit a silently-wrong document.
"""

from __future__ import annotations

import io
from datetime import datetime
from typing import Any

from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, NameObject
from reportlab.pdfgen import canvas

from src.proposals.pdf_stamper import _build_signature_overlay

# reportlab base-14 fonts are the only fonts we support in Phase 1. No
# TTF/non-Latin handling — a glyph outside Latin-1 is deferred/flagged.
_ALLOWED_FONTS = frozenset({"Helvetica", "Courier", "Times-Roman"})
_DEFAULT_FONT = "Helvetica"
# Single-line text/date sizing mirrors the proposals date overlay.
_MIN_FONT_PT = 7.0
_MAX_FONT_PT = 12.0
_LINE_HEIGHT_RATIO = 1.2


def stamp_document(
    source_pdf: bytes,
    fields: list[dict[str, Any]],
    signature_png: bytes | None = None,
) -> bytes:
    """Stamp ``fields`` onto ``source_pdf`` and return flattened PDF bytes.

    Synchronous core (tests call this directly). Async callers should run
    it via ``asyncio.to_thread(stamp_document, ...)``.
    """
    if not source_pdf:
        raise ValueError("source_pdf is empty")

    # Conditional empty-signature guard: only required when a signature
    # field is actually present (unlike the proposals stamper, which
    # always demands a PNG). A field set with no signature stamps fine.
    #
    # Note: this fires for ANY kind=="signature" field, regardless of its
    # ``required`` flag, because signature fields are effectively
    # always-required at stamp time. The backend enforces the
    # requires_esign <-> signature-field consistency invariant (a template
    # that requires e-sign must carry a signature field, and a signature
    # field implies a signature is collected before stamping), so by the
    # time we reach here a present signature field always expects a PNG.
    has_signature_field = any(f.get("kind") == "signature" for f in fields)
    if has_signature_field and signature_png is None:
        raise ValueError("signature image required for signature field")

    reader = PdfReader(io.BytesIO(source_pdf))
    page_count = len(reader.pages)
    if page_count == 0:
        raise ValueError("source_pdf has zero pages")

    # page_idx -> list of overlay PDF bytes to merge onto that page.
    overlays: dict[int, list[bytes]] = {}
    for field in fields:
        page_idx, box = _resolve_box(field, page_count)
        target_page = reader.pages[page_idx]
        page_w = float(target_page.mediabox.width)
        page_h = float(target_page.mediabox.height)
        overlay = _build_field_overlay(
            field, page_w, page_h, box, signature_png
        )
        if overlay is not None:
            overlays.setdefault(page_idx, []).append(overlay)

    writer = PdfWriter()
    for idx, src_page in enumerate(reader.pages):
        for overlay_bytes in overlays.get(idx, []):
            stamp_reader = PdfReader(io.BytesIO(overlay_bytes))
            src_page.merge_page(stamp_reader.pages[0])
        writer.add_page(src_page)

    _flatten(writer)

    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def _resolve_box(
    field: dict[str, Any], page_count: int
) -> tuple[int, tuple[float, float, float, float]]:
    """Translate a stored field to a 0-indexed page + (x, y, w, h) box.

    Same convention as ``service._coords_for_stamper`` (``page - 1``,
    ``w -> width``, ``h -> height``). Raises ``ValueError`` on a page out
    of range or non-positive dimensions — the service validates these at
    save time, so reaching here with bad geometry is fail-closed.
    """
    try:
        page = int(field["page"])
        x = float(field["x"])
        y = float(field["y"])
        w = float(field["w"])
        h = float(field["h"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Malformed field placement: {exc}") from None

    if page < 1 or page > page_count:
        raise ValueError(
            f"Field page {page} outside PDF page range 1-{page_count}"
        )
    if w <= 0 or h <= 0:
        raise ValueError("Field box must have positive width and height")
    return page - 1, (x, y, w, h)


def _build_field_overlay(
    field: dict[str, Any],
    page_w: float,
    page_h: float,
    box: tuple[float, float, float, float],
    signature_png: bytes | None,
) -> bytes | None:
    """Build one overlay PDF for ``field``, or ``None`` to draw nothing.

    Empty values for text/date/address produce no overlay (nothing to
    draw); signature fields always draw the supplied PNG.
    """
    kind = field.get("kind")
    if kind == "signature":
        # Presence of a signature field with a None PNG is rejected
        # upstream in stamp_document, so signature_png is non-None here.
        assert signature_png is not None
        return _build_signature_overlay(
            page_width=page_w,
            page_height=page_h,
            signature_png=signature_png,
            box=box,
        )

    value = field.get("value")
    if value is None or value == "":
        # Fail closed: a *required* field with no value would otherwise
        # stamp a silently-incomplete document, contradicting this module's
        # raise-don't-emit-wrong-output contract. Optional empty fields just
        # draw nothing.
        if field.get("required"):
            raise ValueError(
                f"Required field {field.get('id')!r} has no value to stamp"
            )
        return None
    text = str(value)

    if kind == "date":
        # ISO YYYY-MM-DD -> %m-%d-%Y; fail closed on a malformed date.
        try:
            text = datetime.strptime(text, "%Y-%m-%d").strftime("%m-%d-%Y")
        except ValueError:
            raise ValueError(f"Invalid date value {value!r}; expected YYYY-MM-DD") from None
        return _build_text_overlay(page_w, page_h, box, text, multiline=False)

    if kind == "text":
        return _build_text_overlay(page_w, page_h, box, text, multiline=False)

    if kind == "address":
        return _build_text_overlay(page_w, page_h, box, text, multiline=True)

    raise ValueError(f"Unsupported field kind {kind!r}")


def _build_text_overlay(
    page_w: float,
    page_h: float,
    box: tuple[float, float, float, float],
    text: str,
    *,
    font: str = _DEFAULT_FONT,
    multiline: bool = False,
) -> bytes:
    """Draw ``text`` into ``box`` as a single line or top-down multi-line.

    Fail closed on overflow: if any line is wider than the box, or the
    line count exceeds what the box height holds, raise ``ValueError``
    (no truncation). Coordinates are bottom-left origin (no y-flip).
    """
    if font not in _ALLOWED_FONTS:
        raise ValueError(f"Unsupported font {font!r}")

    x, y, w, h = box
    lines = text.split("\n") if multiline else [text]

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(page_w, page_h))

    if multiline:
        font_size = max(_MIN_FONT_PT, min(_MAX_FONT_PT, h * 0.18))
        line_height = font_size * _LINE_HEIGHT_RATIO
        capacity = int(h // line_height)
        if capacity < 1:
            raise ValueError("Box too short for even one line of text")
        if len(lines) > capacity:
            raise ValueError(
                f"Address needs {len(lines)} lines but box holds {capacity}"
            )
        _assert_lines_fit(c, lines, font, font_size, w)
        c.setFont(font, font_size)
        c.setFillGray(0.0)
        # Render top-down: first line sits near the top of the box, each
        # subsequent line one line-height lower.
        top_baseline = y + h - font_size
        for i, line in enumerate(lines):
            c.drawString(x, top_baseline - i * line_height, line)
    else:
        # Single line, vertically centered like the proposals date stamp.
        font_size = max(_MIN_FONT_PT, min(_MAX_FONT_PT, h * 0.62))
        _assert_lines_fit(c, lines, font, font_size, w)
        c.setFont(font, font_size)
        c.setFillGray(0.0)
        text_y = y + max(0.0, (h - font_size) / 2)
        c.drawString(x, text_y, lines[0])

    c.save()
    return buf.getvalue()


def _assert_lines_fit(
    c: canvas.Canvas,
    lines: list[str],
    font: str,
    font_size: float,
    box_width: float,
) -> None:
    """Raise ``ValueError`` if any line is wider than ``box_width``."""
    for line in lines:
        if c.stringWidth(line, font, font_size) > box_width:
            raise ValueError(
                f"Text {line!r} overflows box width {box_width:.1f}pt"
            )


def _flatten(writer: PdfWriter) -> None:
    """Drop the AcroForm and all Widget annotations from ``writer``.

    Removes ``/AcroForm`` from the document catalog (public
    ``writer.root_object`` on pypdf 6.10.2) and, from each page's
    ``/Annots``, removes only the entries whose ``/Subtype`` is
    ``/Widget`` — keeping links and other annotations. The dropped widget
    objects are cleared in place so the writer doesn't emit a dangling
    ``/Subtype /Widget`` in the output bytes. ``/Annots`` is removed only
    if it becomes empty.

    LIMITATION: a *pre-filled* AcroForm field's visible appearance is dropped
    (we remove the widget rather than rendering its ``/AP`` into the page —
    pypdf 6.10.2 has no reliable API for that). This is correct for the
    intended use case: templates are BLANK forms staff place our own boxes on,
    so there is no pre-filled content to preserve. See
    ``test_flatten_prefilled_widget_loses_appearance``; if pre-filled source
    forms ever need supporting, pre-flatten with Ghostscript/pdftk first.
    """
    root = writer.root_object
    if "/AcroForm" in root:
        del root[NameObject("/AcroForm")]

    for page in writer.pages:
        annots = page.get("/Annots")
        if not annots:
            continue
        kept = ArrayObject()
        for ref in annots:
            obj = ref.get_object()
            if obj.get("/Subtype") == "/Widget":
                obj.clear()
                continue
            kept.append(ref)
        if len(kept) == 0:
            del page[NameObject("/Annots")]
        else:
            page[NameObject("/Annots")] = kept
