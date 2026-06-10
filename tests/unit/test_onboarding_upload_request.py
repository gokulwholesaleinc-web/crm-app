"""No-mock unit tests for the ``upload_request`` DocumentType handler (v3 §B.3).

Covers the pure-handler surface with no client/DB-route boundary: author-time
``validate_definitions`` (flat list, positive maxFiles/maxMB, no PDF read,
shared prefill allow-list), the tolerant ``validate_value``, the
``required_satisfied`` upload-row count gate (0 required ⇒ unmet, ≥1 ⇒ met), and
the brand-headed Platypus manifest from ``produce_artifact`` (lists N files +
the brand company-name present in the PDF bytes when a TenantSettings row
exists). PDFs are real reportlab bytes; the manifest reads real
``OnboardingPacketUpload`` rows from the DB.
"""

from __future__ import annotations

import io
import types
import uuid

import pytest
from pypdf import PdfReader
from src.onboarding.kinds import get_handler
from src.onboarding.kinds.upload_request import (
    UploadRequestDocumentType,
    validate_upload_definitions,
)
from src.onboarding.models import (
    OnboardingPacketDocument,
    OnboardingPacketUpload,
)
from src.onboarding.packet_errors import PacketValidationError
from src.onboarding.service import FieldDefinitionError

HANDLER = UploadRequestDocumentType()


def _pdf_text(data: bytes) -> str:
    """Extract the rendered text from a PDF (robust to Flate-compressed streams)."""
    reader = PdfReader(io.BytesIO(data))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _upload_field(fid: str = "gov_id", *, required: bool = True, **overrides) -> dict:
    field = {
        "id": fid,
        "kind": "file_upload",
        "label": fid.replace("_", " ").title(),
        "required": required,
        "maxFiles": 3,
        "maxMB": 10,
    }
    field.update(overrides)
    return field


# --- validate_definitions: flat list, no PDF, caps --------------------------


def test_validate_definitions_valid_passes():
    """A well-formed file_upload list validates with pdf_bytes=None (no read)."""
    HANDLER.validate_definitions([_upload_field()], pdf_bytes=None)
    validate_upload_definitions([_upload_field()])


def test_validate_definitions_never_reads_pdf_bytes():
    """pdf_bytes is ignored — passing garbage bytes must NOT raise (P0-9)."""
    HANDLER.validate_definitions([_upload_field()], pdf_bytes=b"not a pdf")


def test_validate_definitions_rejects_non_file_field():
    """A non-file_upload field on an upload_request template is rejected."""
    with pytest.raises(FieldDefinitionError):
        validate_upload_definitions([{"id": "x", "kind": "short_text"}])


@pytest.mark.parametrize("cap_key", ["maxFiles", "maxMB"])
@pytest.mark.parametrize("bad", [0, -1, None, "3", 1.5, True])
def test_validate_definitions_rejects_bad_caps(cap_key, bad):
    """maxFiles/maxMB must be positive ints (bool/str/float/0/neg rejected)."""
    field = _upload_field()
    field[cap_key] = bad
    with pytest.raises(FieldDefinitionError):
        validate_upload_definitions([field])


def test_validate_definitions_rejects_cap_over_ceiling():
    """A cap beyond the hard ceiling is rejected."""
    with pytest.raises(FieldDefinitionError):
        validate_upload_definitions([_upload_field(maxMB=10_000)])


def test_validate_definitions_rejects_duplicate_ids():
    with pytest.raises(FieldDefinitionError):
        validate_upload_definitions([_upload_field("a"), _upload_field("a")])


@pytest.mark.parametrize("bad", ["false", "true", 1, 0, "yes", None])
def test_validate_definitions_rejects_non_bool_sensitive(bad):
    """``sensitive`` must be a real bool; stringy values are truthy at fill time."""
    with pytest.raises(FieldDefinitionError):
        validate_upload_definitions([_upload_field(sensitive=bad)])


@pytest.mark.parametrize("ok", [True, False])
def test_validate_definitions_accepts_bool_sensitive(ok):
    """A real bool ``sensitive`` flag is accepted, and absence remains valid."""
    validate_upload_definitions([_upload_field(sensitive=ok)])
    validate_upload_definitions([_upload_field()])


def test_validate_definitions_rejects_pii_prefill():
    """prefill='contact.email' is rejected via the shared ALLOWED_PREFILL."""
    with pytest.raises(FieldDefinitionError):
        validate_upload_definitions([_upload_field(prefill="contact.email")])


def test_validate_definitions_allows_safe_prefill():
    """A whitelisted prefill source is accepted (reuses ALLOWED_PREFILL)."""
    validate_upload_definitions([_upload_field(prefill="contact.name")])


# --- validate_value: tolerant (None | list[int]) ----------------------------


def test_validate_value_none_ok():
    assert HANDLER.validate_value(_upload_field(), None) == (None, None)


def test_validate_value_int_list_ok():
    assert HANDLER.validate_value(_upload_field(), [1, 2, 3]) == ([1, 2, 3], None)


@pytest.mark.parametrize("bad", ["1", {"a": 1}, [1, "2"], [True], 5])
def test_validate_value_rejects_non_int_list(bad):
    with pytest.raises(PacketValidationError):
        HANDLER.validate_value(_upload_field(), bad)


# --- required_satisfied: counts upload ROWS, not the answer list ------------


def _upload_row(field_id: str) -> OnboardingPacketUpload:
    return OnboardingPacketUpload(
        packet_document_id=1,
        field_id=field_id,
        attachment_id=None,
        original_filename="x.pdf",
        byte_size=10,
        content_sha256="0" * 64,
        mime_type="application/pdf",
        sensitive=False,
        token_hash="h",
    )


def test_required_zero_uploads_is_unsatisfied():
    """A required file field with NO upload rows → False."""
    field = _upload_field("gov_id", required=True)
    assert HANDLER.required_satisfied(field, {}, [], None) is False


def test_required_one_upload_is_satisfied():
    """A required file field with ≥1 upload row → True."""
    field = _upload_field("gov_id", required=True)
    uploads = [_upload_row("gov_id")]
    assert HANDLER.required_satisfied(field, {}, uploads, None) is True


def test_required_counts_only_this_field_rows():
    """Rows for a DIFFERENT field don't satisfy this field's requirement."""
    field = _upload_field("gov_id", required=True)
    uploads = [_upload_row("other_field")]
    assert HANDLER.required_satisfied(field, {}, uploads, None) is False


def test_optional_field_is_always_satisfied():
    field = _upload_field("extra", required=False)
    assert HANDLER.required_satisfied(field, {}, [], None) is True


def test_required_satisfied_ignores_stale_answer_ids():
    """A stale id in field_values without a matching row does NOT satisfy."""
    field = _upload_field("gov_id", required=True)
    # field_values claims an upload, but no rows exist → still unmet.
    assert HANDLER.required_satisfied(field, {"gov_id": [99]}, [], None) is False


# --- produce_artifact: brand-headed manifest --------------------------------


async def _persisted_doc(db, defs: list[dict]) -> OnboardingPacketDocument:
    """Persist a minimal upload doc so its real ``id`` keys the upload rows.

    SQLite has FK enforcement OFF in this harness, so a placeholder
    ``packet_id`` (non-null, never dereferenced by the manifest) is enough — the
    handler only reads ``doc.id`` / ``doc.original_filename`` /
    ``doc.field_definitions``.
    """
    doc = OnboardingPacketDocument(
        packet_id=1,
        display_order=0,
        original_filename="Designer Assets.pdf",
        kind="upload_request",
        pdf_path=None,
        field_definitions=defs,
        field_values={},
    )
    db.add(doc)
    await db.flush()
    return doc


@pytest.mark.asyncio
async def test_manifest_lists_files(db_session):
    """The manifest PDF lists each uploaded filename + a count line."""
    defs = [_upload_field("gov_id", label="Government ID")]
    doc = await _persisted_doc(db_session, defs)
    for name in ("passport.pdf", "license.png"):
        db_session.add(
            OnboardingPacketUpload(
                packet_document_id=doc.id,
                field_id="gov_id",
                attachment_id=None,
                original_filename=name,
                byte_size=2048,
                content_sha256="0" * 64,
                mime_type="application/pdf",
                sensitive=False,
                token_hash="h",
            )
        )
    await db_session.flush()

    out = await HANDLER.produce_artifact(
        db_session, doc=doc, packet=types.SimpleNamespace(), signature_png=None
    )
    assert out is not None
    assert out.startswith(b"%PDF")
    text = _pdf_text(out)
    # 2 files received; the count line + both filenames are rendered.
    assert "2 file(s) received" in text
    assert "passport.pdf" in text
    assert "license.png" in text


@pytest.mark.asyncio
async def test_manifest_empty_when_no_uploads(db_session):
    """With no uploaded files the manifest still builds (a 0-file index)."""
    doc = await _persisted_doc(db_session, [_upload_field("gov_id")])
    out = await HANDLER.produce_artifact(
        db_session, doc=doc, packet=types.SimpleNamespace(), signature_png=None
    )
    assert out is not None and out.startswith(b"%PDF")
    assert "0 file(s) received" in _pdf_text(out)


@pytest.mark.asyncio
async def test_manifest_carries_brand_company_name(db_session):
    """When a TenantSettings row exists, its company name is IN the PDF bytes."""
    from src.whitelabel.models import Tenant, TenantSettings

    suffix = uuid.uuid4().hex[:6]
    company = f"LinkCreative {suffix}"
    tenant = Tenant(name=f"T {suffix}", slug=f"t-{suffix}", is_active=True)
    db_session.add(tenant)
    await db_session.flush()
    db_session.add(TenantSettings(tenant_id=tenant.id, company_name=company))
    await db_session.flush()

    doc = await _persisted_doc(db_session, [_upload_field("gov_id")])
    db_session.add(
        OnboardingPacketUpload(
            packet_document_id=doc.id,
            field_id="gov_id",
            attachment_id=None,
            original_filename="passport.pdf",
            byte_size=512,
            content_sha256="0" * 64,
            mime_type="application/pdf",
            sensitive=False,
            token_hash="h",
        )
    )
    await db_session.flush()

    # fetch_logo skipped in dry_run so the test never makes a network call; the
    # company-name header still renders.
    out = await HANDLER.produce_artifact(
        db_session,
        doc=doc,
        packet=types.SimpleNamespace(),
        signature_png=None,
        dry_run=True,
    )
    assert out is not None
    # reportlab embeds the visible text; the brand company name appears.
    assert company in _pdf_text(out)


# --- the live registered instance -------------------------------------------


def test_registered_instance_is_upload_request():
    handler = get_handler("upload_request")
    assert isinstance(handler, UploadRequestDocumentType)
    assert handler.kind == "upload_request"
    assert handler.needs_pdf_copy is False
    assert handler.produces_signature is False
    assert handler.records_view_via_stream is False
