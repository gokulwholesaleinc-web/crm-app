"""Unit tests for ``proposals.pdf_stamper.stamp_master_with_signature``.

Pure-function test: builds a real master PDF + a real PNG signature,
runs the stamper, and asserts the output is a well-formed PDF that
preserves the master's pages, appends one audit page, and never
crashes on edge-case coord payloads.
"""

import hashlib
import io
from datetime import UTC, datetime

import pytest
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas

from src.proposals.pdf_stamper import StampInputs, stamp_master_with_signature

# Minimal 1x1 RGB PNG. The previous RGBA constant decoded under older
# Pillow but raises "broken data stream" on the version pinned in CI,
# breaking reportlab's drawImage path.
_ONE_PIXEL_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010802000000907753de"
    "0000000c49444154789c63f8cfc0000003010100c9fe92ef0000000049454e44ae426082"
)


def _make_master_pdf(page_count: int = 2) -> bytes:
    """Build an in-memory PDF with ``page_count`` blank Letter pages."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    for i in range(page_count):
        c.setFont("Helvetica", 12)
        c.drawString(72, 720, f"Master agreement page {i + 1}")
        c.showPage()
    c.save()
    return buf.getvalue()


def _inputs(
    *,
    master_pdf: bytes | None = None,
    coords: dict | list[dict] | None = None,
    date_coords: dict | list[dict] | None = None,
    date_label: str | None = None,
    signature_png: bytes | None = None,
) -> StampInputs:
    return StampInputs(
        master_pdf=master_pdf if master_pdf is not None else _make_master_pdf(),
        signature_png=signature_png if signature_png is not None else _ONE_PIXEL_PNG,
        coords=coords,
        signer_name="Test Signer",
        signer_email="test@example.com",
        signer_ip="203.0.113.7",
        signer_user_agent="StamperTest/1.0",
        signed_at=datetime(2026, 5, 14, 17, 30, tzinfo=UTC),
        proposal_number="PR-2026-STAMP-1",
        date_coords=date_coords,
        date_label=date_label,
    )


class TestStampMasterWithSignature:
    def test_output_is_well_formed_pdf(self):
        out = stamp_master_with_signature(_inputs())
        assert out.startswith(b"%PDF-")
        # Round-trip parse — corruption would raise here.
        PdfReader(io.BytesIO(out))

    def test_appends_exactly_one_audit_page(self):
        master = _make_master_pdf(page_count=3)
        out = stamp_master_with_signature(_inputs(master_pdf=master))
        reader = PdfReader(io.BytesIO(out))
        # Master pages preserved + one audit page.
        assert len(reader.pages) == 3 + 1

    def test_auto_box_used_when_coords_missing(self):
        """No coords → stamp lands on the last page (auto-detect).

        We don't have a clean way to inspect drawing position without
        rasterizing, so this guards the happy path: the stamper must
        succeed and produce a valid PDF when ``coords`` is None.
        """
        out = stamp_master_with_signature(_inputs(coords=None))
        assert PdfReader(io.BytesIO(out)).pages

    def test_invalid_coords_fall_back_to_auto_box(self):
        """Missing keys / non-numeric values / out-of-range pages all
        fall back to auto-detect instead of raising."""
        out = stamp_master_with_signature(
            _inputs(coords={"page": 99, "x": "nope", "width": -5}),
        )
        assert PdfReader(io.BytesIO(out)).pages

    def test_audit_page_contains_signer_metadata(self):
        out = stamp_master_with_signature(_inputs())
        reader = PdfReader(io.BytesIO(out))
        audit_text = reader.pages[-1].extract_text() or ""
        assert "Test Signer" in audit_text
        assert "test@example.com" in audit_text
        assert "203.0.113.7" in audit_text
        assert "PR-2026-STAMP-1" in audit_text

    def test_date_label_only_renders_when_date_coords_are_supplied(self):
        out_without_date = stamp_master_with_signature(_inputs())
        no_date_text = "\n".join(
            (page.extract_text() or "")
            for page in PdfReader(io.BytesIO(out_without_date)).pages[:-1]
        )
        assert "Signed 2026-05-14" not in no_date_text
        assert "05-14-2026" not in no_date_text

        out_with_date = stamp_master_with_signature(
            _inputs(
                coords={"page": 0, "x": 72, "y": 120, "width": 120, "height": 48},
                date_coords={"page": 0, "x": 240, "y": 120, "width": 90, "height": 24},
                date_label="05-14-2026",
            ),
        )
        date_text = "\n".join(
            (page.extract_text() or "") for page in PdfReader(io.BytesIO(out_with_date)).pages[:-1]
        )
        assert "05-14-2026" in date_text

    def test_multiple_signature_and_date_boxes_render(self):
        out = stamp_master_with_signature(
            _inputs(
                coords=[
                    {"page": 0, "x": 72, "y": 120, "width": 120, "height": 48},
                    {"page": 0, "x": 72, "y": 220, "width": 120, "height": 48},
                ],
                date_coords=[
                    {"page": 0, "x": 240, "y": 120, "width": 90, "height": 24},
                    {"page": 0, "x": 240, "y": 220, "width": 90, "height": 24},
                ],
                date_label="05-14-2026",
            ),
        )
        reader = PdfReader(io.BytesIO(out))
        date_text = "\n".join((page.extract_text() or "") for page in reader.pages[:-1])
        assert date_text.count("05-14-2026") == 2

    def test_audit_page_includes_master_sha256_prefix(self):
        master = _make_master_pdf()
        out = stamp_master_with_signature(_inputs(master_pdf=master))
        reader = PdfReader(io.BytesIO(out))
        audit_text = reader.pages[-1].extract_text() or ""
        digest = hashlib.sha256(master).hexdigest()
        # The stamper prints the first 64 hex chars of the digest.
        assert digest[:64] in audit_text

    def test_rejects_empty_master(self):
        with pytest.raises(ValueError, match="master_pdf"):
            stamp_master_with_signature(_inputs(master_pdf=b""))

    def test_rejects_empty_signature(self):
        with pytest.raises(ValueError, match="signature_png"):
            stamp_master_with_signature(_inputs(signature_png=b""))

    def test_zero_page_master_is_rejected(self):
        """A 'PDF' with valid header but no pages should ValueError
        instead of silently producing a stamp-only output."""
        writer = PdfWriter()
        buf = io.BytesIO()
        writer.write(buf)
        with pytest.raises(ValueError, match="zero pages"):
            stamp_master_with_signature(_inputs(master_pdf=buf.getvalue()))
