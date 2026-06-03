"""No-mock unit tests for the ``questionnaire`` DocumentType handler (v3 §B, P2).

The questionnaire kind is the de-PDF intake form: typed questions, choice
answers, an "Other" write-in, sensitive (encrypt-at-rest) fields, and a BRANDED
reportlab Platypus answer-summary PDF at completion. These tests are no-mock —
``validate_value`` coercion runs against real pydantic adapters, ``produce_artifact``
renders a REAL PDF through a REAL DB session (for the brand header), and the
crypto path uses the real ``ONBOARDING_FIELD_KEY`` Fernet primitive.

Coverage (matches the §H test strategy):
  * validate_value: email/url garbage → 422; maxLength; single/multi membership;
    ``__other__`` requires a non-empty write-in; sensitive → ciphertext with the
    plaintext absent from field_values.
  * required_satisfied: empty list unmet; multi + ``__other__``-no-writein unmet;
    a sensitive required field met via the ``secrets`` arg only.
  * produce_artifact GOLDEN-PDF: an overflowing paragraph + a 10-item multi-select
    render WITHOUT truncation/fail-close; a sentinel password is ABSENT from the
    bytes; the brand company-name is PRESENT when a TenantSettings row exists;
    ``dry_run=True`` raises cleanly on a forced content error without writing an
    Attachment.
  * validate_definitions: ``prefill:"contact.email"`` rejected at template-save.
"""

import types

import pytest
from src.onboarding import crypto
from src.onboarding.kinds import get_handler
from src.onboarding.kinds.questionnaire import (
    OTHER_TOKEN,
    QuestionnaireDocumentType,
    validate_questionnaire_definitions,
)
from src.onboarding.limits import MAX_TEXT_VALUE_BYTES
from src.onboarding.packet_errors import PacketValidationError
from src.onboarding.service import FieldDefinitionError

HANDLER = QuestionnaireDocumentType()


# --- field builders --------------------------------------------------------


def _text(fid: str = "name", kind: str = "short_text", **over) -> dict:
    field = {"id": fid, "kind": kind, "label": fid.title(), "required": True}
    field.update(over)
    return field


def _choice(fid: str, kind: str, *, options=("a", "b"), allow_other=False, **over) -> dict:
    field = {
        "id": fid,
        "kind": kind,
        "label": fid.title(),
        "required": True,
        "allow_other": allow_other,
        "options": [{"value": v, "label": v.upper()} for v in options],
    }
    field.update(over)
    return field


# --- metadata + registration ----------------------------------------------


def test_kind_metadata():
    """The handler advertises a no-PDF, no-signature, /viewed-recording kind."""
    assert HANDLER.kind == "questionnaire"
    assert HANDLER.needs_pdf_copy is False
    assert HANDLER.produces_signature is False
    assert HANDLER.records_view_via_stream is False


def test_registered_in_kind_handlers():
    """The module-level HANDLER auto-registers under its kind."""
    registered = get_handler("questionnaire")
    assert isinstance(registered, QuestionnaireDocumentType)


# --- validate_value: text + format coercion --------------------------------


def test_short_text_returns_plaintext_no_cipher():
    assert HANDLER.validate_value(_text("name"), "Jane") == ("Jane", None)


def test_none_clears_field():
    assert HANDLER.validate_value(_text("name"), None) == (None, None)


@pytest.mark.parametrize("bad", [123, ["x"], 4.5, True])
def test_text_non_string_raises(bad):
    with pytest.raises(PacketValidationError):
        HANDLER.validate_value(_text("name"), bad)


def test_email_valid_passes():
    field = _text("email", kind="email")
    assert HANDLER.validate_value(field, "a@b.com") == ("a@b.com", None)


@pytest.mark.parametrize("garbage", ["not-an-email", "a@", "@b.com", "a b@c.com"])
def test_email_garbage_422(garbage):
    """A malformed email is a real format 422, not just a non-empty check."""
    field = _text("email", kind="email")
    with pytest.raises(PacketValidationError):
        HANDLER.validate_value(field, garbage)


def test_url_valid_passes():
    field = _text("site", kind="url")
    assert HANDLER.validate_value(field, "https://example.com/x") == (
        "https://example.com/x",
        None,
    )


@pytest.mark.parametrize("garbage", ["not a url", "://nope", "http://"])
def test_url_garbage_422(garbage):
    field = _text("site", kind="url")
    with pytest.raises(PacketValidationError):
        HANDLER.validate_value(field, garbage)


def test_date_valid_iso_passes():
    field = _text("when", kind="date")
    assert HANDLER.validate_value(field, "2026-06-03") == ("2026-06-03", None)


@pytest.mark.parametrize("garbage", ["06/03/2026", "2026-13-01", "tomorrow"])
def test_date_garbage_422(garbage):
    field = _text("when", kind="date")
    with pytest.raises(PacketValidationError):
        HANDLER.validate_value(field, garbage)


def test_max_length_enforced():
    field = _text("note", maxLength=10)
    assert HANDLER.validate_value(field, "x" * 10) == ("x" * 10, None)
    with pytest.raises(PacketValidationError):
        HANDLER.validate_value(field, "x" * 11)


def test_byte_cap_enforced():
    """The shared UTF-8 byte cap is the hard ceiling even with no maxLength."""
    field = _text("note")
    over = "x" * (MAX_TEXT_VALUE_BYTES + 1)
    with pytest.raises(PacketValidationError):
        HANDLER.validate_value(field, over)


# --- validate_value: choice membership + Other -----------------------------


def test_single_choice_member_passes():
    assert HANDLER.validate_value(_choice("c", "single_choice"), "a") == ("a", None)


def test_single_choice_unknown_option_422():
    with pytest.raises(PacketValidationError):
        HANDLER.validate_value(_choice("c", "single_choice"), "zzz")


def test_single_choice_bare_other_token_422():
    """A lone ``__other__`` with no write-in is incomplete (must send the dict)."""
    field = _choice("c", "single_choice", allow_other=True)
    with pytest.raises(PacketValidationError):
        HANDLER.validate_value(field, OTHER_TOKEN)


def test_single_choice_other_dict_passes():
    field = _choice("c", "single_choice", allow_other=True)
    out, cipher = HANDLER.validate_value(field, {"value": OTHER_TOKEN, "other": "x"})
    assert out == {"value": OTHER_TOKEN, "other": "x"} and cipher is None


def test_single_choice_other_empty_writein_422():
    field = _choice("c", "single_choice", allow_other=True)
    with pytest.raises(PacketValidationError):
        HANDLER.validate_value(field, {"value": OTHER_TOKEN, "other": "  "})


def test_other_rejected_when_not_allowed():
    field = _choice("c", "single_choice", allow_other=False)
    with pytest.raises(PacketValidationError):
        HANDLER.validate_value(field, {"value": OTHER_TOKEN, "other": "x"})


def test_multi_choice_list_passes_and_dedups():
    field = _choice("c", "multi_choice", options=("a", "b", "c"))
    out, _ = HANDLER.validate_value(field, ["a", "b", "a"])
    assert out == ["a", "b"]  # de-duplicated, order preserved


def test_multi_choice_other_writein_dedups_inner_list():
    """BUG 2: a multi_choice {value, other} write-in de-dupes its inner list.

    The previous code validated the inner list (which de-dupes) but then stored
    the RAW ``inner`` verbatim, so a payload with duplicate selections persisted
    the dupes. The returned ``value`` list must be de-duplicated (order
    preserved) and still carry ``__other__`` so the write-in renders.
    """
    field = _choice("c", "multi_choice", options=("a", "b", "c"), allow_other=True)
    out, cipher = HANDLER.validate_value(
        field, {"value": ["a", "a", OTHER_TOKEN], "other": "x"}
    )
    assert cipher is None
    assert out["other"] == "x"
    assert out["value"] == ["a", OTHER_TOKEN]  # de-duped, order preserved
    # The dup is gone — exactly one "a".
    assert out["value"].count("a") == 1


def test_multi_choice_non_list_422():
    with pytest.raises(PacketValidationError):
        HANDLER.validate_value(_choice("c", "multi_choice"), "a")


def test_multi_choice_unknown_member_422():
    with pytest.raises(PacketValidationError):
        HANDLER.validate_value(_choice("c", "multi_choice"), ["a", "nope"])


def test_multi_choice_other_dict_passes():
    field = _choice("c", "multi_choice", options=("a", "b"), allow_other=True)
    out, _ = HANDLER.validate_value(
        field, {"value": ["a", OTHER_TOKEN], "other": "extra"}
    )
    assert out == {"value": ["a", OTHER_TOKEN], "other": "extra"}


def test_multi_choice_other_dict_without_token_422():
    """An Other write-in must include the ``__other__`` token in the selection."""
    field = _choice("c", "multi_choice", options=("a", "b"), allow_other=True)
    with pytest.raises(PacketValidationError):
        HANDLER.validate_value(field, {"value": ["a"], "other": "extra"})


# --- validate_value: sensitive → ciphertext --------------------------------


def test_sensitive_returns_ciphertext_plaintext_dropped():
    """A sensitive answer encrypts; the plaintext is never returned for storage."""
    field = _text("pw", sensitive=True)
    plaintext, ciphertext = HANDLER.validate_value(field, "hunter2")
    assert plaintext is None
    assert isinstance(ciphertext, bytes) and ciphertext
    # And it round-trips through the real crypto primitive.
    assert crypto.decrypt_field(ciphertext) == "hunter2"


def test_sensitive_plaintext_absent_from_ciphertext():
    field = _text("pw", sensitive=True)
    _, ciphertext = HANDLER.validate_value(field, "PlainSecret123")
    assert b"PlainSecret123" not in ciphertext


# --- required_satisfied ----------------------------------------------------


def test_required_empty_string_unmet():
    assert HANDLER.required_satisfied(_text("n"), {"n": "  "}, None, None) is False


def test_required_missing_unmet():
    assert HANDLER.required_satisfied(_text("n"), {}, None, None) is False


def test_required_present_met():
    assert HANDLER.required_satisfied(_text("n"), {"n": "Jane"}, None, None) is True


def test_optional_empty_met():
    field = _text("n", required=False)
    assert HANDLER.required_satisfied(field, {}, None, None) is True


def test_required_empty_list_unmet():
    field = _choice("c", "multi_choice")
    assert HANDLER.required_satisfied(field, {"c": []}, None, None) is False


def test_required_non_empty_list_met():
    field = _choice("c", "multi_choice")
    assert HANDLER.required_satisfied(field, {"c": ["a"]}, None, None) is True


def test_required_multi_other_no_writein_unmet():
    field = _choice("c", "multi_choice", allow_other=True)
    val = {"value": ["a", OTHER_TOKEN], "other": ""}
    assert HANDLER.required_satisfied(field, {"c": val}, None, None) is False


def test_required_multi_other_with_writein_met():
    field = _choice("c", "multi_choice", allow_other=True)
    val = {"value": ["a", OTHER_TOKEN], "other": "extra"}
    assert HANDLER.required_satisfied(field, {"c": val}, None, None) is True


def test_required_sensitive_met_only_via_secrets():
    field = _text("pw", sensitive=True)
    # field_values never holds the secret → unmet without a secrets entry.
    assert HANDLER.required_satisfied(field, {}, None, None) is False
    assert HANDLER.required_satisfied(field, {}, None, {}) is False
    assert HANDLER.required_satisfied(field, {}, None, {"pw": b"cipher"}) is True


# --- validate_definitions: author-time (no PDF read) -----------------------


def test_definitions_valid_pass():
    defs = [
        _text("name"),
        _choice("chans", "multi_choice", options=("seo", "ppc"), allow_other=True),
    ]
    HANDLER.validate_definitions(defs, pdf_bytes=None)  # never reads pdf_bytes


def test_definitions_duplicate_id_raises():
    with pytest.raises(FieldDefinitionError):
        validate_questionnaire_definitions([_text("dup"), _text("dup")])


def test_definitions_unknown_kind_raises():
    with pytest.raises(FieldDefinitionError):
        validate_questionnaire_definitions([_text("x", kind="signature")])


def test_definitions_choice_without_options_raises():
    bad = {"id": "c", "kind": "single_choice", "label": "C", "required": True}
    with pytest.raises(FieldDefinitionError):
        validate_questionnaire_definitions([bad])


def test_definitions_allow_other_on_text_raises():
    with pytest.raises(FieldDefinitionError):
        validate_questionnaire_definitions([_text("n", allow_other=True)])


@pytest.mark.parametrize("kind", ["single_choice", "multi_choice"])
def test_definitions_sensitive_on_choice_kind_raises(kind):
    """Q1: ``sensitive`` is only valid on a text field — a sensitive choice could
    never be filled (encryption coerces to str), so reject it at author time."""
    field = _choice("secret_choice", kind, options=("a", "b"), sensitive=True)
    with pytest.raises(FieldDefinitionError, match="sensitive is only valid on text"):
        validate_questionnaire_definitions([field])


@pytest.mark.parametrize("kind", ["short_text", "paragraph", "email", "url", "date"])
def test_definitions_sensitive_on_text_kinds_pass(kind):
    """A sensitive flag IS accepted on every text kind (F4 passwords are text)."""
    validate_questionnaire_definitions([_text("secret", kind=kind, sensitive=True)])


def test_definitions_reserved_other_token_as_option_raises():
    bad = _choice("c", "single_choice", options=("a",))
    bad["options"].append({"value": OTHER_TOKEN, "label": "Other"})
    with pytest.raises(FieldDefinitionError):
        validate_questionnaire_definitions([bad])


def test_definitions_pii_prefill_rejected():
    """A questionnaire field with ``prefill:'contact.email'`` is rejected at save."""
    field = _text("email", kind="email", prefill="contact.email")
    with pytest.raises(FieldDefinitionError):
        validate_questionnaire_definitions([field])


def test_definitions_allowed_prefill_passes():
    field = _text("full_name", prefill="contact.name")
    validate_questionnaire_definitions([field])


# --- produce_artifact: golden PDF (real DB session for the brand header) ----


def _golden_defs() -> list[dict]:
    return [
        {"id": "name", "kind": "short_text", "label": "Client Name",
         "required": True, "section_id": "b", "section_label": "Basics"},
        {"id": "long", "kind": "paragraph", "label": "Long Answer",
         "required": True, "section_id": "b", "section_label": "Basics"},
        {"id": "chans", "kind": "multi_choice", "label": "Channels",
         "required": True, "allow_other": True, "section_id": "m",
         "section_label": "Marketing",
         "options": [{"value": f"o{i}", "label": f"Option {i}"} for i in range(10)]},
        {"id": "opt", "kind": "short_text", "label": "Optional Field",
         "required": False, "section_id": "m", "section_label": "Marketing"},
        {"id": "pw", "kind": "short_text", "label": "Password", "required": True,
         "sensitive": True, "section_id": "c", "section_label": "Credentials"},
    ]


def _pdf_text(pdf_bytes: bytes) -> str:
    """Extract the rendered text from a PDF (reportlab compresses content
    streams, so a raw-byte substring can't find rendered text — extract it)."""
    import io

    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def _golden_doc() -> types.SimpleNamespace:
    return types.SimpleNamespace(
        original_filename="Client Strategy Insights",
        field_definitions=_golden_defs(),
        # 10-item multi-select + an overflowing paragraph; ``opt`` omitted (→ "—");
        # ``pw`` never stored (sensitive — its plaintext is structurally absent).
        field_values={
            "name": "Jane Doe",
            "long": ("word " * 500).strip(),
            "chans": [f"o{i}" for i in range(10)],
        },
    )


@pytest.mark.asyncio
async def test_produce_artifact_golden_pdf_no_truncation(db_session, test_tenant):
    """Overflowing paragraph + 10-item multi render WITHOUT truncation/fail-close,
    and the brand company-name is PRESENT (resolved from TenantSettings)."""
    out = await HANDLER.produce_artifact(
        db_session, doc=_golden_doc(), packet=None, signature_png=None,
        dry_run=False,
    )
    assert out is not None
    assert out.startswith(b"%PDF")
    text = _pdf_text(out)
    # The brand header resolves "Test Tenant Inc" from the TenantSettings row the
    # ``test_tenant`` fixture creates (single-tenant brand source).
    assert "Test Tenant Inc" in text
    # All 10 multi-select labels render (nothing truncated/fail-closed); the
    # last option proves the list rendered in full.
    assert "Option 9" in text
    # The optional omitted field renders the em-dash placeholder, not broken UI.
    assert "—" in text


@pytest.mark.asyncio
async def test_produce_artifact_omits_sensitive_plaintext(db_session, test_tenant):
    """A sensitive plaintext present in the doc's values is NEVER in the output.

    Even if a stray plaintext leaked into ``field_values`` (it must not), the
    renderer's sensitive branch prints the placeholder and never the value.
    """
    doc = _golden_doc()
    # Force a sentinel into field_values for the sensitive field to prove the
    # renderer's allow-list redaction wins regardless of what's in the JSONB.
    doc.field_values["pw"] = "SENTINEL_PASSWORD_DO_NOT_LEAK"
    out = await HANDLER.produce_artifact(
        db_session, doc=doc, packet=None, signature_png=None, dry_run=False,
    )
    text = _pdf_text(out)
    assert "SENTINEL_PASSWORD_DO_NOT_LEAK" not in text
    assert "provided" in text  # the "provided — stored securely" placeholder


@pytest.mark.asyncio
async def test_produce_artifact_dry_run_no_attachment(db_session, test_tenant):
    """dry_run=True renders bytes (producibility) and writes NO Attachment row."""
    from sqlalchemy import func, select
    from src.attachments.models import Attachment

    before = (await db_session.execute(select(func.count(Attachment.id)))).scalar()
    out = await HANDLER.produce_artifact(
        db_session, doc=_golden_doc(), packet=None, signature_png=None,
        dry_run=True,
    )
    assert out is not None and out.startswith(b"%PDF")
    after = (await db_session.execute(select(func.count(Attachment.id)))).scalar()
    assert after == before  # the handler never creates an Attachment


@pytest.mark.asyncio
async def test_produce_artifact_renders_pathological_content_no_raise(
    db_session, test_tenant
):
    """Pathological answers (an unbreakable mega-token, injection-style markup)
    render WITHOUT raising — the Platypus path WRAPS rather than fail-closing
    (the spec's explicit contract vs. the stamper's overflow-block), the escaped
    markup can't inject reportlab tags, and dry_run still writes no Attachment.

    This is the questionnaire's real Phase-A guarantee: by completion the answers
    are already fill-time-validated (``validate_value``), so the producibility
    dry-run proves the render is robust, not that it fail-closes.
    """
    from sqlalchemy import func, select
    from src.attachments.models import Attachment

    doc = _golden_doc()
    # A single unbreakable 5k-char token + a tag-injection attempt: both must
    # render cleanly (wrapped / escaped), never raise.
    doc.field_values["name"] = "x" * 5000
    doc.field_values["long"] = "<para>not a real tag</para> & <b>bold?</b>"
    before = (await db_session.execute(select(func.count(Attachment.id)))).scalar()
    out = await HANDLER.produce_artifact(
        db_session, doc=doc, packet=None, signature_png=None, dry_run=True,
    )
    assert out is not None and out.startswith(b"%PDF")
    after = (await db_session.execute(select(func.count(Attachment.id)))).scalar()
    assert after == before  # dry_run writes no Attachment


# --- scrub: questionnaire RETAINS non-sensitive answers (§C.5) --------------


@pytest.mark.asyncio
async def test_scrub_retains_field_values():
    """Unlike esign, a questionnaire keeps its answers for later querying."""
    doc = types.SimpleNamespace(field_values={"name": "Jane", "ch": ["a", "b"]})
    await HANDLER.scrub(None, doc=doc)
    assert doc.field_values == {"name": "Jane", "ch": ["a", "b"]}
