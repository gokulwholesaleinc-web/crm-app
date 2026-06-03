"""``esign_pdf`` DocumentType — the original PDF-stamp document as a plugin.

e-sign is demoted from *the* model to *one* document kind. P0 EXTRACTS the
existing inline stamp/validate/required/scrub logic into this handler with
**no behavior change** (the methods are byte-faithful to the pre-v3 paths). P1
rewires the live call sites to delegate here and removes the transient
duplication; with only ``esign_pdf`` registered, the existing suite stays green
= the byte-identical regression baseline.

Discipline (§B.1): kind-specific indexing of ``field_definitions``/
``field_values`` (``field["page"]``, ``values[id].strip()``) lives ONLY in this
handler — never in the kind-agnostic core.
"""

from __future__ import annotations

import asyncio
import io
import math
from typing import TYPE_CHECKING

from pypdf import PdfReader

# Import ONLY leaf modules at top level — the ``kinds`` package is imported by
# the registry self-test (and by tests) in import orders the app never hits, so
# pulling ``packet_service``/``service``/``stamper`` here would drag the app
# router graph into the chain and trip pre-existing circular imports. The heavy
# deps (the 422 error class, the stamper, storage) are lazy-imported inside the
# methods, where the app graph is already initialized.
from src.onboarding.limits import MAX_TEXT_VALUE_BYTES
from src.onboarding.packet_errors import PacketValidationError
from src.onboarding.prefill import ALLOWED_PREFILL

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.onboarding.models import OnboardingPacket, OnboardingPacketDocument


def _fields_with_values(doc: OnboardingPacketDocument) -> list[dict]:
    """Inject saved ``field_values`` into each field-definition's ``value``.

    The stamper reads ``field["value"]`` for non-signature kinds; signature
    fields draw the packet's PNG (passed separately). Byte-faithful copy of the
    pre-v3 ``completion._fields_with_values`` (removed there in P1).
    """
    values = doc.field_values or {}
    out: list[dict] = []
    for field in doc.field_definitions or []:
        merged = dict(field)
        if field.get("kind") != "signature":
            merged["value"] = values.get(field.get("id"))
        out.append(merged)
    return out


def validate_esign_definitions(
    defs: list[dict], pdf_bytes: bytes | None
) -> None:
    """Geometry / bounds / uniqueness / prefill checks → ``FieldDefinitionError``.

    Branches on ``pdf_bytes is None`` FIRST (P0-9: never read a missing PDF).
    Reuses the shared ``ALLOWED_PREFILL`` (never a local copy → ``email``/PII can
    never be made prefillable). Extracted verbatim from the pre-v3
    ``OnboardingTemplateService._validate_field_definitions`` so behavior is
    unchanged; P1 makes that method delegate here.
    """
    # Lazy (author-time only) — keeps the module's top-level imports leaf-only.
    from src.onboarding.service import FieldDefinitionError

    if pdf_bytes is None:
        raise FieldDefinitionError(
            "Upload a PDF before defining fields on this template."
        )
    reader = PdfReader(io.BytesIO(pdf_bytes))
    page_count = len(reader.pages)
    seen_ids: set[str | None] = set()

    for index, field in enumerate(defs):
        label = f"field '{field.get('id', index)}'"

        field_id = field.get("id")
        if field_id in seen_ids:
            raise FieldDefinitionError(f"Duplicate field id '{field_id}'")
        seen_ids.add(field_id)

        if field.get("prefill") not in (None, *ALLOWED_PREFILL):
            raise FieldDefinitionError(
                f"{label}: unsupported prefill '{field.get('prefill')}'"
            )

        page = field.get("page")
        if not isinstance(page, int) or page < 1 or page > page_count:
            raise FieldDefinitionError(
                f"{label}: page {page} out of range (1..{page_count})"
            )

        try:
            x = float(field["x"])
            y = float(field["y"])
            w = float(field["w"])
            h = float(field["h"])
        except (KeyError, TypeError, ValueError) as exc:
            raise FieldDefinitionError(f"{label}: malformed coordinates") from exc

        if not all(math.isfinite(v) for v in (x, y, w, h)):
            raise FieldDefinitionError(f"{label}: non-finite coordinates")
        if w <= 0 or h <= 0:
            raise FieldDefinitionError(
                f"{label}: width and height must be positive"
            )

        media_box = reader.pages[page - 1].mediabox
        page_w = float(media_box.width)
        page_h = float(media_box.height)
        if x < 0 or y < 0 or x + w > page_w or y + h > page_h:
            raise FieldDefinitionError(
                f"{label}: box is outside the page bounds "
                f"({page_w:.0f}x{page_h:.0f} pt)"
            )


class EsignPdfDocumentType:
    """The PDF-stamp + drawn-signature document kind."""

    kind = "esign_pdf"
    needs_pdf_copy = True  # copy the template PDF into the packet doc
    produces_signature = True
    records_view_via_stream = True  # the legally-meaningful /pdf read-before-sign

    def validate_definitions(
        self, defs: list[dict], *, pdf_bytes: bytes | None
    ) -> None:
        validate_esign_definitions(defs, pdf_bytes)

    def validate_value(
        self, field: dict, value: object
    ) -> tuple[object, bytes | None]:
        """String-only per the pre-v3 wire contract; ``None`` clears a field.

        Returns ``(plaintext_for_jsonb, ciphertext)`` — esign never produces
        ciphertext. Byte-faithful to the per-field branch of
        ``packet_service._validate_field_values``.
        """
        fid = field.get("id")
        if value is not None and not isinstance(value, str):
            raise PacketValidationError(f"Field '{fid}' has an invalid value")
        if (
            isinstance(value, str)
            and len(value.encode("utf-8")) > MAX_TEXT_VALUE_BYTES
        ):
            raise PacketValidationError(f"Field '{fid}' value is too long")
        return value, None

    def required_satisfied(
        self,
        field: dict,
        values: dict,
        uploads: list | None = None,
        secrets: dict | None = None,
    ) -> bool:
        """A required non-signature field needs a non-empty string value.

        Signature presence is a PACKET-level check (``_assert_signature_present``)
        — return True here. Mirrors the per-field branch of
        ``completion._validate_documents_for_completion``.
        """
        if field.get("kind") == "signature":
            return True
        if not field.get("required"):
            return True
        val = (values or {}).get(field.get("id"))
        return not (val is None or (isinstance(val, str) and not val.strip()))

    async def produce_artifact(
        self,
        db: AsyncSession,
        *,
        doc: OnboardingPacketDocument,
        packet: OnboardingPacket,
        signature_png: bytes | None,
        dry_run: bool = False,
    ) -> bytes | None:
        """Stamp + flatten the filled PDF. ``dry_run`` produces identical bytes
        (the caller discards them) so a content error (bad date / overflow /
        undecodable PNG) surfaces in Phase A. Reads storage only — no ``db``.
        """
        # Lazy — keeps the module's top-level imports leaf-only (storage and the
        # stamper both reach into the app graph).
        from src.onboarding import storage
        from src.onboarding.stamper import stamp_document

        # An esign doc ALWAYS has a per-packet PDF copy (needs_pdf_copy=True);
        # a NULL here is a real defect, not a questionnaire/upload doc routed
        # wrongly. Guard so it surfaces as a clean failure (pdf_path is nullable
        # in the schema now that non-esign kinds carry no copy).
        if doc.pdf_path is None:
            raise RuntimeError(f"esign_pdf document {doc.id} has no PDF copy")
        source = await storage.read_bytes(doc.pdf_path)
        fields = _fields_with_values(doc)
        return await asyncio.to_thread(stamp_document, source, fields, signature_png)

    async def scrub(
        self, db: AsyncSession, *, doc: OnboardingPacketDocument
    ) -> None:
        """Null the recipient answers (PII scrub). The drawn signature is nulled
        at the PACKET level by ``scrub_packet``. No uploads/secrets for esign.
        """
        doc.field_values = {}


# Discovered + registered by the kinds package auto-loader (it reads this
# module-level ``HANDLER``). Deliberately NO import from ``src.onboarding.kinds``
# here so handler modules stay leaf and discovery is cycle-free.
HANDLER = EsignPdfDocumentType()
