"""No-mock unit tests for the onboarding PDF stamper.

Pure-function tests: each builds its source PDF in-test with reportlab
(already a dependency), calls the synchronous ``stamp_document`` core
directly, and parses the output back with pypdf. No DB, no mocks.
"""

import io

import pytest
from pypdf import PdfReader
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas
from src.onboarding.stamper import stamp_document

# --- in-test PDF + image builders (no fixtures, no mocks) ------------------


def _base_pdf(pages: int = 1) -> bytes:
    """A plain multi-page PDF with no form fields."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER)
    for i in range(pages):
        c.drawString(72, 720, f"Base page {i + 1}")
        c.showPage()
    c.save()
    return buf.getvalue()


def _acroform_pdf() -> bytes:
    """A PDF that actually contains an AcroForm text-field widget.

    Used so the flatten assertions (no /AcroForm, no /Subtype /Widget)
    are meaningful — the source genuinely has a widget to remove.
    """
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER)
    c.drawString(72, 720, "Form below:")
    c.acroForm.textfield(
        name="ein", x=72, y=600, width=200, height=20, borderStyle="inset"
    )
    c.showPage()
    c.save()
    return buf.getvalue()


def _png_bytes() -> bytes:
    """A tiny opaque PNG (1x1 red) for signature fields."""
    # Minimal valid PNG produced by reportlab is overkill; hand-roll a
    # 1x1 red PNG so we avoid Pillow as a hard test dependency.
    import struct
    import zlib

    width = height = 1
    raw = b"\x00" + b"\xff\x00\x00"  # filter byte + one RGB pixel
    compressed = zlib.compress(raw)

    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(
            ">I", zlib.crc32(body) & 0xFFFFFFFF
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", compressed)
        + chunk(b"IEND", b"")
    )


def _field(kind: str, **overrides) -> dict:
    """A field dict with sane defaults for the given kind."""
    base = {
        "id": f"f_{kind}",
        "kind": kind,
        "label": kind.title(),
        "required": False,
        "prefill": None,
        "page": 1,
        "x": 72.0,
        "y": 144.0,
        "w": 200.0,
        "h": 40.0,
    }
    base.update(overrides)
    return base


def _assert_valid_pdf(data: bytes, expected_pages: int) -> PdfReader:
    assert data, "stamper returned empty bytes"
    reader = PdfReader(io.BytesIO(data))
    assert len(reader.pages) == expected_pages
    return reader


# --- per-kind: each kind stamps and yields a valid PDF ---------------------


def test_signature_field_stamps_valid_pdf():
    """Should stamp a signature field and preserve page count."""
    fields = [_field("signature")]
    out = stamp_document(_base_pdf(), fields, signature_png=_png_bytes())
    _assert_valid_pdf(out, expected_pages=1)


def test_text_field_stamps_valid_pdf():
    """Should stamp a single-line text field."""
    fields = [_field("text", value="Acme LLC")]
    out = stamp_document(_base_pdf(), fields)
    reader = _assert_valid_pdf(out, expected_pages=1)
    assert "Acme LLC" in reader.pages[0].extract_text()


def test_address_field_multiline_stamps_valid_pdf():
    """Should stamp a multi-line address field top-down."""
    fields = [_field("address", value="123 Main St\nSuite 200\nChicago, IL", h=60.0)]
    out = stamp_document(_base_pdf(), fields)
    text = _assert_valid_pdf(out, expected_pages=1).pages[0].extract_text()
    assert "123 Main St" in text
    assert "Suite 200" in text
    assert "Chicago, IL" in text


def test_date_field_stamps_valid_pdf():
    """Should stamp a date field."""
    fields = [_field("date", value="2026-05-29")]
    out = stamp_document(_base_pdf(), fields)
    _assert_valid_pdf(out, expected_pages=1)


def test_multipage_preserves_page_count():
    """Should preserve page count when stamping a multi-page PDF."""
    fields = [_field("text", value="Page two field", page=2)]
    out = stamp_document(_base_pdf(pages=3), fields)
    _assert_valid_pdf(out, expected_pages=3)


# --- date reformat ---------------------------------------------------------


def test_date_iso_reformatted_to_us_format():
    """Should reformat ISO YYYY-MM-DD to %m-%d-%Y in the output text."""
    fields = [_field("date", value="2026-05-29")]
    out = stamp_document(_base_pdf(), fields)
    text = PdfReader(io.BytesIO(out)).pages[0].extract_text()
    assert "05-29-2026" in text
    assert "2026-05-29" not in text


def test_invalid_date_raises():
    """Should raise ValueError on a non-ISO date (fail closed)."""
    fields = [_field("date", value="29/05/2026")]
    with pytest.raises(ValueError):
        stamp_document(_base_pdf(), fields)


# --- conditional empty-signature guard -------------------------------------


def test_no_signature_field_set_stamps_without_png():
    """Should stamp a field set with no signature field given png=None."""
    fields = [_field("text", value="Acme"), _field("date", value="2026-01-01")]
    out = stamp_document(_base_pdf(), fields, signature_png=None)
    _assert_valid_pdf(out, expected_pages=1)


def test_signature_field_without_png_raises():
    """Should raise when a signature field is present but png is None."""
    fields = [_field("signature")]
    with pytest.raises(ValueError):
        stamp_document(_base_pdf(), fields, signature_png=None)


# --- fail-closed overflow (no truncation) ----------------------------------


def test_oversize_single_line_text_raises():
    """Should raise when single-line text is wider than its box."""
    fields = [_field("text", value="X" * 400, w=60.0, h=20.0)]
    with pytest.raises(ValueError):
        stamp_document(_base_pdf(), fields)


def test_address_too_many_lines_raises():
    """Should raise when an address needs more lines than the box holds."""
    long_address = "\n".join(f"Line {i}" for i in range(40))
    fields = [_field("address", value=long_address, h=30.0)]
    with pytest.raises(ValueError):
        stamp_document(_base_pdf(), fields)


def test_address_line_too_wide_raises():
    """Should raise when one address line is wider than the box."""
    fields = [_field("address", value="short\n" + "Z" * 400, w=60.0, h=60.0)]
    with pytest.raises(ValueError):
        stamp_document(_base_pdf(), fields)


# --- flatten: no AcroForm, no Widget ---------------------------------------


def test_flatten_removes_acroform_and_widget():
    """Should strip /AcroForm and all /Widget annots from a form PDF."""
    source = _acroform_pdf()
    # Sanity: the source genuinely has the form artifacts we expect to drop.
    src_reader = PdfReader(io.BytesIO(source))
    assert "/AcroForm" in src_reader.trailer["/Root"]
    assert b"/Widget" in source

    fields = [_field("text", value="filled", page=1)]
    out = stamp_document(source, fields)

    # Raw-bytes assertions per the spec.
    assert b"/AcroForm" not in out
    assert b"/Subtype /Widget" not in out
    assert b"/Widget" not in out

    # Catalog-level assertion + page count preserved.
    out_reader = _assert_valid_pdf(out, expected_pages=1)
    assert "/AcroForm" not in out_reader.trailer["/Root"]


def test_flatten_keeps_non_widget_annotations():
    """Should keep link annotations while dropping only widgets."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER)
    c.drawString(72, 720, "Has a link and a widget")
    c.linkURL("https://example.com", (72, 700, 200, 718), relative=0)
    c.acroForm.textfield(name="ein", x=72, y=600, width=200, height=20)
    c.showPage()
    c.save()
    source = buf.getvalue()

    out = stamp_document(source, [_field("text", value="x")])

    assert b"/Widget" not in out
    # The link survives.
    out_reader = PdfReader(io.BytesIO(out))
    annots = out_reader.pages[0].get("/Annots")
    assert annots is not None
    subtypes = {a.get_object().get("/Subtype") for a in annots}
    assert "/Link" in subtypes
    assert "/Widget" not in subtypes


def test_blank_acroform_flattens_cleanly():
    """Should flatten a BLANK (no value) AcroForm form to a static PDF.

    This is the intended use case: templates ship as blank forms onto
    which staff place our own overlay boxes. A blank widget carries no
    visible text, so dropping it loses nothing — the result is a valid,
    static, AcroForm-free document.
    """
    source = _acroform_pdf()  # textfield with NO value
    # Sanity: the blank widget genuinely has no value to lose.
    src_annots = PdfReader(io.BytesIO(source)).pages[0].get("/Annots")
    assert all(a.get_object().get("/V") in (None, "") for a in src_annots)

    out = stamp_document(source, [_field("text", value="placed by staff")])

    out_reader = _assert_valid_pdf(out, expected_pages=1)
    assert "/AcroForm" not in out_reader.trailer["/Root"]
    assert b"/Widget" not in out
    # Our own overlay content is what survives.
    assert "placed by staff" in out_reader.pages[0].extract_text()


def test_flatten_prefilled_widget_loses_appearance():
    """Documents the known limitation: a PRE-FILLED widget's visible value
    is dropped on flatten (not rendered into page content).

    pypdf 6.10.2 has no reliable API to render a widget's ``/AP /N``
    appearance into the page, so ``_flatten`` removes the widget wholesale.
    For the intended blank-form workflow this is correct; this test pins
    the behavior so a future change to render-on-flatten is a deliberate,
    test-breaking decision rather than a silent one.
    """
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER)
    c.drawString(72, 720, "Pre-filled form:")
    # A field WITH a value -> the source carries a visible /V + /AP /N.
    c.acroForm.textfield(
        name="ein", value="12-3456789", x=72, y=600, width=200, height=20
    )
    c.showPage()
    c.save()
    source = buf.getvalue()

    # Sanity: the prefilled value is present and visible in the SOURCE.
    src_reader = PdfReader(io.BytesIO(source))
    src_annot = src_reader.pages[0].get("/Annots")[0].get_object()
    assert src_annot.get("/V") == "12-3456789"
    assert "/AP" in src_annot

    out = stamp_document(source, [_field("text", value="ours")])
    out_reader = _assert_valid_pdf(out, expected_pages=1)

    # The widget (and thus its rendered appearance) is gone.
    assert b"/Widget" not in out
    assert "/AcroForm" not in out_reader.trailer["/Root"]
    # Documented loss: the pre-filled value does not survive in any layer.
    assert "12-3456789" not in out_reader.pages[0].extract_text()
    # Our own overlay, by contrast, IS preserved.
    assert "ours" in out_reader.pages[0].extract_text()


# --- edge inputs -----------------------------------------------------------


def test_empty_source_pdf_raises():
    """Should raise on empty source bytes."""
    with pytest.raises(ValueError):
        stamp_document(b"", [_field("text", value="x")])


def test_page_out_of_range_raises():
    """Should raise when a field targets a non-existent page."""
    fields = [_field("text", value="x", page=5)]
    with pytest.raises(ValueError):
        stamp_document(_base_pdf(pages=1), fields)


def test_empty_value_skips_overlay_but_stays_valid():
    """Should stamp nothing for an empty (optional) text value yet stay valid."""
    fields = [_field("text", value="")]
    out = stamp_document(_base_pdf(), fields)
    _assert_valid_pdf(out, expected_pages=1)


def test_required_field_with_empty_value_raises():
    """Should fail closed when a REQUIRED field has no value to stamp."""
    fields = [_field("text", value="", required=True)]
    with pytest.raises(ValueError):
        stamp_document(_base_pdf(), fields)


def test_required_field_with_missing_value_key_raises():
    """Should fail closed when a required field omits the value key entirely."""
    field = _field("date", required=True)
    field.pop("value", None)
    with pytest.raises(ValueError):
        stamp_document(_base_pdf(), [field])
