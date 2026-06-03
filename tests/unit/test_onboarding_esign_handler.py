"""No-mock unit tests for the ``esign_pdf`` DocumentType handler (v3 §B, P0).

P0 EXTRACTS the pre-v3 inline stamp/validate/required/scrub logic into one
handler with **no behavior change**. These tests prove the extraction is
byte-faithful to those inline paths: validate_value mirrors the per-field wire
branch of ``packet_service``, required_satisfied mirrors the completion
per-field branch, validate_definitions mirrors the template coord validator,
and produce_artifact's output is asserted byte-identical to an independent
``stamp_document`` call over the same merged fields. No mocks; PDFs are real
reportlab bytes written through real ``onboarding.storage``.
"""

import asyncio
import types
import uuid

import pytest
from src.onboarding import storage
from src.onboarding.kinds import get_handler
from src.onboarding.kinds.esign_pdf import (
    EsignPdfDocumentType,
    validate_esign_definitions,
)
from src.onboarding.limits import MAX_TEXT_VALUE_BYTES
from src.onboarding.packet_errors import PacketValidationError
from src.onboarding.service import FieldDefinitionError
from src.onboarding.stamper import stamp_document
from unit._onboarding_helpers import (
    one_page_pdf,
    signature_field,
    text_field,
)

HANDLER = EsignPdfDocumentType()


# --- validate_value: string-only wire contract -----------------------------


def test_validate_value_str_returns_plaintext_no_cipher():
    """A str value returns ``(the_str, None)`` (esign never produces ciphertext)."""
    field = text_field("full_name")
    assert HANDLER.validate_value(field, "Jane Doe") == ("Jane Doe", None)


def test_validate_value_none_returns_none_none():
    """``None`` clears a field → ``(None, None)``."""
    field = text_field("full_name")
    assert HANDLER.validate_value(field, None) == (None, None)


@pytest.mark.parametrize("bad_value", [123, ["a"], {"k": "v"}, 4.5, True])
def test_validate_value_non_str_raises(bad_value):
    """A non-str, non-None value → PacketValidationError (422, not silent coerce)."""
    field = text_field("full_name")
    with pytest.raises(PacketValidationError):
        HANDLER.validate_value(field, bad_value)


def test_validate_value_at_byte_cap_is_accepted():
    """A value exactly at MAX_TEXT_VALUE_BYTES is still accepted (boundary)."""
    field = text_field("notes")
    value = "x" * MAX_TEXT_VALUE_BYTES  # ASCII → 1 byte/char, exactly the cap
    assert HANDLER.validate_value(field, value) == (value, None)


def test_validate_value_over_byte_cap_raises():
    """A value over MAX_TEXT_VALUE_BYTES UTF-8 bytes → PacketValidationError."""
    field = text_field("notes")
    value = "x" * (MAX_TEXT_VALUE_BYTES + 1)
    with pytest.raises(PacketValidationError):
        HANDLER.validate_value(field, value)


def test_validate_value_byte_cap_counts_utf8_not_chars():
    """The cap is on UTF-8 BYTES: multibyte chars trip it below the char count."""
    # Each '€' is 3 UTF-8 bytes; just over the cap in bytes, well under in chars.
    field = text_field("notes")
    chars = (MAX_TEXT_VALUE_BYTES // 3) + 1
    value = "€" * chars
    assert len(value) < MAX_TEXT_VALUE_BYTES  # under the limit by char count
    assert len(value.encode("utf-8")) > MAX_TEXT_VALUE_BYTES  # over it in bytes
    with pytest.raises(PacketValidationError):
        HANDLER.validate_value(field, value)


# --- required_satisfied: completion gate -----------------------------------


def test_required_missing_value_is_unsatisfied():
    """Required + value absent from the map → False."""
    field = text_field("full_name", required=True)
    assert HANDLER.required_satisfied(field, {}, None, None) is False


def test_required_empty_string_is_unsatisfied():
    """Required + empty string → False."""
    field = text_field("full_name", required=True)
    assert HANDLER.required_satisfied(field, {"full_name": ""}, None, None) is False


def test_required_whitespace_only_is_unsatisfied():
    """Required + whitespace-only string → False (stripped check)."""
    field = text_field("full_name", required=True)
    assert (
        HANDLER.required_satisfied(field, {"full_name": "   \t\n"}, None, None)
        is False
    )


def test_required_non_empty_is_satisfied():
    """Required + a real value → True."""
    field = text_field("full_name", required=True)
    assert (
        HANDLER.required_satisfied(field, {"full_name": "Jane"}, None, None) is True
    )


def test_signature_field_is_always_satisfied():
    """A signature-kind field is satisfied here (signature is a packet check)."""
    field = signature_field("client_sig")
    # Even with no value present, the per-field gate returns True for signatures.
    assert HANDLER.required_satisfied(field, {}, None, None) is True


def test_optional_empty_field_is_satisfied():
    """An OPTIONAL field with no value → True (nothing to require)."""
    field = text_field("middle_name", required=False)
    assert HANDLER.required_satisfied(field, {}, None, None) is True


# --- validate_definitions: author-time geometry / bounds / prefill ---------


def test_validate_definitions_valid_coords_pass():
    """In-bounds coords on a real one-page PDF validate cleanly."""
    pdf = one_page_pdf()
    HANDLER.validate_definitions([text_field("full_name")], pdf_bytes=pdf)
    # The module function and the handler method must agree (handler delegates).
    validate_esign_definitions([text_field("full_name")], pdf)


def test_validate_definitions_none_pdf_raises():
    """pdf_bytes=None → FieldDefinitionError BEFORE any PDF read (P0-9)."""
    with pytest.raises(FieldDefinitionError):
        HANDLER.validate_definitions([text_field("full_name")], pdf_bytes=None)


def test_validate_definitions_out_of_bounds_box_raises():
    """A box that spills off the page (huge x/w) → FieldDefinitionError."""
    pdf = one_page_pdf()
    field = text_field("full_name", x=600.0, w=400.0)  # x+w far past 612pt width
    with pytest.raises(FieldDefinitionError):
        HANDLER.validate_definitions([field], pdf_bytes=pdf)


def test_validate_definitions_duplicate_id_raises():
    """Two fields with the same id → FieldDefinitionError."""
    pdf = one_page_pdf()
    defs = [text_field("dup", y=100.0), text_field("dup", y=300.0)]
    with pytest.raises(FieldDefinitionError):
        HANDLER.validate_definitions(defs, pdf_bytes=pdf)


def test_validate_definitions_pii_prefill_raises():
    """prefill='contact.email' → FieldDefinitionError (PII is never prefillable)."""
    pdf = one_page_pdf()
    field = text_field("email", prefill="contact.email")
    with pytest.raises(FieldDefinitionError):
        HANDLER.validate_definitions([field], pdf_bytes=pdf)


def test_validate_definitions_page_out_of_range_raises():
    """A page beyond the PDF's page count → FieldDefinitionError."""
    pdf = one_page_pdf()  # single page
    field = text_field("full_name", page=5)
    with pytest.raises(FieldDefinitionError):
        HANDLER.validate_definitions([field], pdf_bytes=pdf)


# --- produce_artifact: stamped PDF, byte-identical to the inline path -------


async def _write_source_pdf() -> tuple[str, bytes]:
    """Write a real one-page PDF to storage and return (key, source_bytes)."""
    source_bytes = one_page_pdf()
    key = f"onboarding_packets/test/{uuid.uuid4().hex}.pdf"
    pdf_path = await storage.write(key, source_bytes, "application/pdf")
    return pdf_path, source_bytes


def _doc_for(pdf_path: str) -> types.SimpleNamespace:
    """A stand-in OnboardingPacketDocument with the fields the handler reads.

    produce_artifact only touches ``.id``, ``.pdf_path``, ``.field_definitions``
    and ``.field_values`` — no DB, so a SimpleNamespace is faithful.
    """
    return types.SimpleNamespace(
        id=1,
        pdf_path=pdf_path,
        field_definitions=[text_field("full_name")],
        field_values={"full_name": "Jane Doe"},
    )


@pytest.mark.asyncio
async def test_produce_artifact_returns_stamped_pdf():
    """produce_artifact returns real flattened PDF bytes (starts with %PDF)."""
    pdf_path, _ = await _write_source_pdf()
    try:
        doc = _doc_for(pdf_path)
        out = await HANDLER.produce_artifact(
            None, doc=doc, packet=types.SimpleNamespace(), signature_png=None
        )
        assert out is not None
        assert out.startswith(b"%PDF")
    finally:
        await storage.delete(pdf_path)


@pytest.mark.asyncio
async def test_produce_artifact_is_byte_identical_to_inline_stamp():
    """The extracted handler output equals an independent stamp_document call.

    This is the regression baseline: the merged field set the handler builds
    (field_definitions with saved field_values injected as ``value``) stamped
    with the same source must be byte-for-byte identical to the pre-v3 inline
    path. If a future refactor diverges, this test breaks deliberately.
    """
    pdf_path, source_bytes = await _write_source_pdf()
    try:
        doc = _doc_for(pdf_path)

        # Independently reproduce the handler's field-merge (the same logic as
        # esign_pdf._fields_with_values) and stamp directly.
        values = doc.field_values
        merged = []
        for field in doc.field_definitions:
            m = dict(field)
            if field.get("kind") != "signature":
                m["value"] = values.get(field.get("id"))
            merged.append(m)
        expected = await asyncio.to_thread(
            stamp_document, source_bytes, merged, None
        )

        out = await HANDLER.produce_artifact(
            None, doc=doc, packet=None, signature_png=None
        )
        assert out == expected
    finally:
        await storage.delete(pdf_path)


@pytest.mark.asyncio
async def test_produce_artifact_dry_run_returns_same_bytes():
    """dry_run=True produces identical bytes (the caller discards them)."""
    pdf_path, _ = await _write_source_pdf()
    try:
        doc = _doc_for(pdf_path)
        wet = await HANDLER.produce_artifact(
            None, doc=doc, packet=None, signature_png=None
        )
        dry = await HANDLER.produce_artifact(
            None, doc=doc, packet=None, signature_png=None, dry_run=True
        )
        assert dry == wet
    finally:
        await storage.delete(pdf_path)


# --- scrub: nulls the recipient answers ------------------------------------


@pytest.mark.asyncio
async def test_scrub_nulls_field_values():
    """scrub empties field_values (PII scrub); no uploads/secrets for esign."""
    doc = types.SimpleNamespace(field_values={"a": "x", "b": "secret"})
    await HANDLER.scrub(None, doc=doc)
    assert doc.field_values == {}


# --- the live registered instance behaves identically ----------------------


def test_registered_instance_matches_class_behavior():
    """The instance in KIND_HANDLERS is an EsignPdfDocumentType with the contract."""
    registered = get_handler("esign_pdf")
    assert isinstance(registered, EsignPdfDocumentType)
    assert registered.validate_value(text_field("x"), "ok") == ("ok", None)
