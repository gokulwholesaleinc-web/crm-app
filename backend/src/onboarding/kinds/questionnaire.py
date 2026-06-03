"""``questionnaire`` DocumentType — Lorenzo's web intake forms as a plugin (P2).

A questionnaire is the OPPOSITE shape from ``esign_pdf``: there is no template
PDF and no signature ceremony. The recipient answers an ordered list of typed
questions (short/paragraph text, single/multi choice, date, email, url) grouped
into sections; on completion this handler renders a BRANDED reportlab Platypus
summary PDF that lands as one Attachment under the contact (same surface as the
e-sign form).

Discipline (§B.1): kind-specific indexing of ``field_definitions`` /
``field_values`` (``field["options"]``, the ``{value, other}`` answer shape)
lives ONLY in this handler — never in the kind-agnostic core.

Leaf module: imports NOTHING from ``src.onboarding.kinds`` so package
auto-discovery stays cycle-free. The heavy reportlab/branding deps are imported
lazily inside ``produce_artifact`` (the app graph is initialized by then); the
self-test only touches the lightweight metadata + the pure validators.

Answer-shape contract (LOCKED by the architect — see §A.6 / §B.3):
  * ``short_text`` / ``paragraph`` / ``date`` / ``email`` / ``url`` → ``str``
  * ``single_choice``           → an option ``value`` ``str``
  * ``multi_choice``            → a ``list[str]`` of option values
  * "Other" write-in            → a ``{"value": <str | list[str]>, "other": <str>}``
    DICT stored under the field's OWN id (NOT a sibling ``__other__`` key). The
    ``"__other__"`` reserved token is the selected value (single) or appears in
    the selected list (multi); ``other`` carries the non-empty write-in text.
  * ``sensitive`` text          → never stored in ``field_values``; the plaintext
    is encrypted (``crypto.encrypt_field``) and returned as the ciphertext half
    of ``validate_value``; the summary PDF renders "provided — stored securely".
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import AnyUrl, EmailStr, TypeAdapter, ValidationError

from src.onboarding import crypto
from src.onboarding.limits import MAX_TEXT_VALUE_BYTES
from src.onboarding.packet_errors import PacketValidationError
from src.onboarding.prefill import ALLOWED_PREFILL

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.onboarding.models import OnboardingPacket, OnboardingPacketDocument

# The question kinds a questionnaire field may declare. ``dropdown`` is folded
# into ``single_choice`` + ``display:"dropdown"`` (§7.3) — identical answer
# shape — so it is deliberately NOT a kind here.
TEXT_KINDS = frozenset({"short_text", "paragraph", "email", "url", "date"})
CHOICE_KINDS = frozenset({"single_choice", "multi_choice"})
ALLOWED_KINDS = TEXT_KINDS | CHOICE_KINDS

# Reserved option token that means "the recipient chose Other and wrote in a
# value". It may be the lone single-choice value or appear inside a multi_choice
# list; the write-in then lives in the answer dict's ``other`` key.
OTHER_TOKEN = "__other__"

# Default max chars for a free-text answer when a field declares no ``maxLength``
# (paragraph answers can be long; the hard ceiling is the UTF-8 byte cap shared
# with esign so one questionnaire field can't blow the body cap).
_DEFAULT_MAX_LENGTH = 5000

# EmailStr / AnyUrl can't be instantiated directly; a module-level TypeAdapter
# is the pydantic-v2 way to validate a bare scalar (and it is reused, not rebuilt
# per call). A bad value raises ``ValidationError`` → a clean 422 (not just a
# non-empty check) per the format-coercion contract.
_EMAIL_ADAPTER = TypeAdapter(EmailStr)
_URL_ADAPTER = TypeAdapter(AnyUrl)


def _field_id(field: dict, index: int | None = None) -> str:
    fid = field.get("id")
    return str(fid) if fid is not None else f"#{index}"


def _option_values(field: dict) -> set[str]:
    """The set of declared option ``value`` strings for a choice field."""
    values: set[str] = set()
    for opt in field.get("options") or []:
        if isinstance(opt, dict) and isinstance(opt.get("value"), str):
            values.add(opt["value"])
    return values


def validate_questionnaire_definitions(defs: list[dict]) -> None:
    """Author-time validation for a questionnaire field list (P0-9: no PDF read).

    Validates id-slug uniqueness, kind membership, well-formed choice options,
    ``allow_other`` only on choice kinds, and reuses the shared
    ``ALLOWED_PREFILL`` so ``email``/PII can never be made prefillable. Raises
    ``FieldDefinitionError`` (→ 422) at template-save, mirroring the esign coords
    validator's contract.
    """
    # Lazy (author-time only) — keeps this module's top-level imports leaf-only
    # and avoids dragging ``service`` into the kinds import chain.
    from src.onboarding.service import FieldDefinitionError

    seen_ids: set[str] = set()
    for index, field in enumerate(defs):
        if not isinstance(field, dict):
            raise FieldDefinitionError(f"field #{index} is not an object")
        label = f"field '{_field_id(field, index)}'"

        fid = field.get("id")
        if not isinstance(fid, str) or not fid:
            raise FieldDefinitionError(f"{label}: missing or non-string id")
        if fid in seen_ids:
            raise FieldDefinitionError(f"Duplicate field id '{fid}'")
        seen_ids.add(fid)

        kind = field.get("kind")
        if kind not in ALLOWED_KINDS:
            raise FieldDefinitionError(
                f"{label}: unsupported questionnaire kind '{kind}'"
            )

        # Prefill PII rule (§D.5): reuse the SHARED allow-list — never a local
        # copy — so ``contact.email`` (or any future PII source) stays rejected.
        prefill = field.get("prefill")
        if prefill not in (None, *ALLOWED_PREFILL):
            raise FieldDefinitionError(
                f"{label}: unsupported prefill '{prefill}'"
            )

        is_choice = kind in CHOICE_KINDS
        if is_choice:
            options = field.get("options")
            if not isinstance(options, list) or not options:
                raise FieldDefinitionError(
                    f"{label}: a {kind} field needs a non-empty options list"
                )
            opt_values: set[str] = set()
            for opt in options:
                if (
                    not isinstance(opt, dict)
                    or not isinstance(opt.get("value"), str)
                    or not opt["value"]
                    or not isinstance(opt.get("label"), str)
                    or not opt["label"]
                ):
                    raise FieldDefinitionError(
                        f"{label}: each option needs a non-empty "
                        "string value and label"
                    )
                if opt["value"] == OTHER_TOKEN:
                    raise FieldDefinitionError(
                        f"{label}: '{OTHER_TOKEN}' is reserved; set "
                        "allow_other instead of declaring it as an option"
                    )
                if opt["value"] in opt_values:
                    raise FieldDefinitionError(
                        f"{label}: duplicate option value '{opt['value']}'"
                    )
                opt_values.add(opt["value"])
        elif field.get("allow_other"):
            # ``allow_other`` only makes sense on a choice kind (it adds the
            # Other write-in path); on a text kind it is a definition error.
            raise FieldDefinitionError(
                f"{label}: allow_other is only valid on choice fields"
            )


class QuestionnaireDocumentType:
    """The web-questionnaire document kind (no PDF, no signature)."""

    kind = "questionnaire"
    needs_pdf_copy = False  # no template PDF to copy → pdf_path stays NULL
    produces_signature = False
    records_view_via_stream = False  # records on POST /viewed, not /pdf

    def validate_definitions(
        self, defs: list[dict], *, pdf_bytes: bytes | None
    ) -> None:
        # Branch BEFORE any PDF read (P0-9): a questionnaire never has a PDF, so
        # ``pdf_bytes`` is ignored entirely — never opened.
        validate_questionnaire_definitions(defs)

    def validate_value(
        self, field: dict, value: object
    ) -> tuple[object, bytes | None]:
        """Fill-time per-field wire + format check → ``(plaintext, ciphertext)``.

        A sensitive field returns ``(None, ciphertext)`` so its plaintext NEVER
        enters ``field_values``; every other kind returns ``(coerced, None)``.
        ``None`` clears a field (the recipient unset an optional answer).
        Garbage email/url is a 422 (real format coercion), not just non-empty.
        """
        fid = _field_id(field)
        kind = field.get("kind")
        if kind not in ALLOWED_KINDS:
            # A stored definition somehow carries a bad kind — fail closed rather
            # than silently accept an un-renderable answer.
            raise PacketValidationError(
                f"Field '{fid}' has an unsupported kind '{kind}'"
            )

        if value is None:
            return None, None

        if field.get("sensitive"):
            # Sensitive text → encrypt; the plaintext never enters field_values.
            # Coerce to str first (the same per-kind shape as a non-sensitive
            # text field) so a non-string sensitive payload is a clean 422.
            plaintext = self._coerce_text(field, value)
            try:
                ciphertext, _version = crypto.encrypt_field(plaintext)
            except crypto.OnboardingCryptoError as exc:
                # ONBOARDING_FIELD_KEY unset/invalid → fail closed (never store
                # or accept the plaintext). Surfaced as a 422 without echoing the
                # value (§D.2 log hygiene).
                raise PacketValidationError(
                    f"Field '{fid}' is sensitive and cannot be accepted right "
                    "now; please contact support."
                ) from exc
            return None, ciphertext

        if kind in CHOICE_KINDS:
            return self._coerce_choice(field, value), None
        return self._coerce_text(field, value), None

    def _coerce_text(self, field: dict, value: object) -> str:
        """Validate a non-choice answer to a ``str`` (with email/url/date format)."""
        fid = _field_id(field)
        kind = field.get("kind")
        if not isinstance(value, str):
            raise PacketValidationError(f"Field '{fid}' must be text")
        if len(value.encode("utf-8")) > MAX_TEXT_VALUE_BYTES:
            raise PacketValidationError(f"Field '{fid}' value is too long")
        max_length = field.get("maxLength")
        if not isinstance(max_length, int) or max_length <= 0:
            max_length = _DEFAULT_MAX_LENGTH
        if len(value) > max_length:
            raise PacketValidationError(
                f"Field '{fid}' exceeds its {max_length}-character limit"
            )
        if kind == "email" and value.strip():
            try:
                _EMAIL_ADAPTER.validate_python(value.strip())
            except ValidationError as exc:
                raise PacketValidationError(
                    f"Field '{fid}' is not a valid email address"
                ) from exc
        if kind == "url" and value.strip():
            try:
                _URL_ADAPTER.validate_python(value.strip())
            except ValidationError as exc:
                raise PacketValidationError(
                    f"Field '{fid}' is not a valid URL"
                ) from exc
        if kind == "date" and value.strip():
            # ISO 8601 date (``YYYY-MM-DD``) — stored as the string the FE's
            # ``<input type=date>`` emits; rendered via the locale formatter.
            from datetime import date

            try:
                date.fromisoformat(value.strip())
            except ValueError as exc:
                raise PacketValidationError(
                    f"Field '{fid}' is not a valid ISO date (YYYY-MM-DD)"
                ) from exc
        return value

    def _coerce_choice(self, field: dict, value: object) -> object:
        """Validate a choice answer: a value str, a value list, or {value, other}.

        Membership is checked against the declared option values; the reserved
        ``__other__`` token is accepted only when the field is ``allow_other`` and
        then requires a non-empty ``other`` write-in.
        """
        fid = _field_id(field)
        kind = field.get("kind")
        allow_other = bool(field.get("allow_other"))
        option_values = _option_values(field)

        if isinstance(value, dict):
            # The {value, other} write-in shape. ``value`` is the selection(s),
            # ``other`` the non-empty write-in text.
            return self._coerce_choice_with_other(
                field, value, kind, allow_other, option_values
            )

        if kind == "single_choice":
            if not isinstance(value, str):
                raise PacketValidationError(
                    f"Field '{fid}' must be a single selected option"
                )
            self._assert_option_member(fid, value, allow_other, option_values)
            if value == OTHER_TOKEN:
                # Bare ``__other__`` with no write-in is incomplete — the FE must
                # send the {value, other} dict. Reject so an empty Other can't
                # masquerade as an answer.
                raise PacketValidationError(
                    f"Field '{fid}': please fill in the Other value"
                )
            return value

        # multi_choice → a list of option values.
        if not isinstance(value, list):
            raise PacketValidationError(
                f"Field '{fid}' must be a list of selected options"
            )
        return self._coerce_multi_list(fid, value, allow_other, option_values)

    def _coerce_choice_with_other(
        self,
        field: dict,
        value: dict,
        kind: object,
        allow_other: bool,
        option_values: set[str],
    ) -> dict:
        fid = _field_id(field)
        if not allow_other:
            raise PacketValidationError(
                f"Field '{fid}' does not accept an Other write-in"
            )
        inner = value.get("value")
        other = value.get("other")
        if not isinstance(other, str) or not other.strip():
            raise PacketValidationError(
                f"Field '{fid}': the Other value cannot be empty"
            )
        if len(other.encode("utf-8")) > MAX_TEXT_VALUE_BYTES:
            raise PacketValidationError(f"Field '{fid}' Other value is too long")

        if kind == "single_choice":
            if inner != OTHER_TOKEN:
                raise PacketValidationError(
                    f"Field '{fid}': an Other write-in requires the Other option"
                )
            normalized_inner: object = OTHER_TOKEN
        else:  # multi_choice
            if not isinstance(inner, list):
                raise PacketValidationError(
                    f"Field '{fid}' selections must be a list"
                )
            # Use the coerced (validated + de-duplicated) list — the previous
            # code discarded this and stored the raw ``inner`` verbatim, so a
            # payload with duplicate selections was persisted with the dupes.
            coerced = self._coerce_multi_list(fid, inner, allow_other, option_values)
            if OTHER_TOKEN not in coerced:
                raise PacketValidationError(
                    f"Field '{fid}': an Other write-in requires the Other option "
                    "to be selected"
                )
            normalized_inner = coerced
        return {"value": normalized_inner, "other": other}

    def _coerce_multi_list(
        self,
        fid: str,
        value: list,
        allow_other: bool,
        option_values: set[str],
    ) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for item in value:
            if not isinstance(item, str):
                raise PacketValidationError(
                    f"Field '{fid}' selections must be option strings"
                )
            self._assert_option_member(fid, item, allow_other, option_values)
            if item not in seen:
                seen.add(item)
                out.append(item)
        return out

    @staticmethod
    def _assert_option_member(
        fid: str, value: str, allow_other: bool, option_values: set[str]
    ) -> None:
        if value == OTHER_TOKEN:
            if not allow_other:
                raise PacketValidationError(
                    f"Field '{fid}' does not accept an Other option"
                )
            return
        if value not in option_values:
            raise PacketValidationError(
                f"Field '{fid}' has an unknown option '{value}'"
            )

    def required_satisfied(
        self,
        field: dict,
        values: dict,
        uploads: list | None = None,
        secrets: dict | None = None,
    ) -> bool:
        """Completion gate (P0-1/P0-8): non-empty str / non-empty list / a
        sensitive field met iff its ciphertext is present in ``secrets``.

        ``__other__`` selected requires the non-empty write-in. An OPTIONAL field
        with no answer is satisfied (nothing to require).
        """
        if not field.get("required"):
            return True
        fid = field.get("id")

        if field.get("sensitive"):
            # A sensitive value never lands in field_values — its ciphertext is
            # the proof of submission. ``secrets`` is the field_id→ciphertext map
            # the secret table holds (P3 wires it through; in v1 it may be None).
            return bool(secrets) and fid in secrets

        val = (values or {}).get(fid)
        if val is None:
            return False

        if isinstance(val, dict):
            # {value, other} write-in shape.
            inner = val.get("value")
            other = val.get("other")
            if not isinstance(other, str) or not other.strip():
                return False
            if isinstance(inner, list):
                return len(inner) > 0
            return bool(inner)

        if isinstance(val, list):
            return len(val) > 0

        if isinstance(val, str):
            return bool(val.strip())

        return False

    async def produce_artifact(
        self,
        db: AsyncSession,
        *,
        doc: OnboardingPacketDocument,
        packet: OnboardingPacket,
        signature_png: bytes | None,
        dry_run: bool = False,
    ) -> bytes | None:
        """Render the BRANDED reportlab Platypus answer-summary PDF (P0-3).

        Platypus ``Paragraph``/``Frame`` flowables WRAP long answers (never the
        stamper's fail-closed overflow that would block completion). The
        LinkCreative brand header is PREPENDED via the shared
        ``brand_header_flowables`` (DRY — the same ``TenantSettings`` source as
        the web fill page). ``dry_run=True`` skips the network logo fetch and
        builds into a throwaway buffer to check producibility WITHOUT writing an
        Attachment. A render/content error raises so Phase A surfaces it as a
        clean 422 (status unchanged), never a stranded ``completing``.
        """
        # Lazy import: reportlab + branding both reach into the app graph; keep
        # this module's top-level imports leaf-only for cycle-free discovery.
        import io

        from reportlab.lib.colors import HexColor
        from reportlab.lib.enums import TA_LEFT
        from reportlab.lib.pagesizes import LETTER
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

        from src.onboarding.pdf_branding import brand_header_flowables

        styles = getSampleStyleSheet()
        section_style = ParagraphStyle(
            "OnbSection",
            parent=styles["Heading2"],
            spaceBefore=14,
            spaceAfter=4,
            alignment=TA_LEFT,
        )
        question_style = ParagraphStyle(
            "OnbQuestion",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=13,
            spaceBefore=8,
            spaceAfter=1,
        )
        answer_style = ParagraphStyle(
            "OnbAnswer",
            parent=styles["Normal"],
            fontSize=10,
            leading=14,
            spaceAfter=2,
            textColor=HexColor("#1f2937"),
        )

        # The brand header degrades gracefully and never fails the artifact; the
        # logo fetch is skipped on the dry-run (it can't affect producibility).
        flow = await brand_header_flowables(db, fetch_logo=not dry_run)
        flow.append(
            Paragraph(self._escape(doc.original_filename or "Questionnaire"),
                      styles["Title"])
        )
        flow.append(Spacer(1, 0.1 * inch))

        values = doc.field_values or {}
        last_section: object = object()  # sentinel: never equals a real id
        for field in doc.field_definitions or []:
            section_id = field.get("section_id")
            if section_id != last_section:
                label = field.get("section_label") or section_id
                if label:
                    flow.append(Paragraph(self._escape(str(label)), section_style))
                last_section = section_id

            flow.append(
                Paragraph(
                    self._escape(field.get("label") or field.get("id") or ""),
                    question_style,
                )
            )
            flow.extend(
                self._render_answer(
                    field, values.get(field.get("id")), answer_style
                )
            )

        target = io.BytesIO()
        SimpleDocTemplate(
            target,
            pagesize=LETTER,
            leftMargin=0.9 * inch,
            rightMargin=0.9 * inch,
            topMargin=0.8 * inch,
            bottomMargin=0.8 * inch,
            title=doc.original_filename or "Questionnaire",
        ).build(flow)
        return target.getvalue()

    def _render_answer(self, field: dict, value: object, answer_style) -> list:
        """Flowables for one answer — wraps long text, bullets multi-select,
        redacts sensitive, ``—`` for an empty optional."""
        from reportlab.platypus import Paragraph

        if field.get("sensitive"):
            # The plaintext is structurally absent from field_values (§D.2); the
            # summary states it was collected without ever rendering the secret.
            return [Paragraph("provided — stored securely", answer_style)]

        if value is None or value in ("", []):
            return [Paragraph("—", answer_style)]

        if isinstance(value, dict):
            # {value, other} write-in shape.
            inner = value.get("value")
            other = value.get("other") or ""
            if isinstance(inner, list):
                items = [
                    self._escape(f"Other: {other}") if raw == OTHER_TOKEN
                    else self._escape(self._option_label(field, raw))
                    for raw in inner
                ]
                return [self._bulleted(items, answer_style)]
            # single Other write-in
            return [Paragraph(self._escape(f"Other: {other}"), answer_style)]

        if isinstance(value, list):
            items = [self._escape(self._option_label(field, v)) for v in value]
            if not items:
                return [Paragraph("—", answer_style)]
            return [self._bulleted(items, answer_style)]

        # A plain string answer (single_choice value or free text). For a
        # single_choice the stored value is the option ``value`` — render its
        # human label.
        text = self._option_label(field, str(value))
        return [Paragraph(self._escape(text), answer_style)]

    @staticmethod
    def _bulleted(items: list[str], answer_style):
        from reportlab.platypus import ListFlowable, ListItem, Paragraph

        list_items: list[ListItem] = [
            ListItem(Paragraph(it, answer_style), leftIndent=12) for it in items
        ]
        # reportlab's ListFlowable accepts a list of ListItem at runtime; its
        # stub types the arg narrowly as ``Iterable[_NestedFlowable]``.
        return ListFlowable(
            list_items,  # type: ignore[arg-type]
            bulletType="bullet",
            start="•",
            leftIndent=14,
        )

    @staticmethod
    def _option_label(field: dict, value: str) -> str:
        """Map a stored choice ``value`` to its human ``label`` (presentation-only;
        a label edit never orphans the stored value — §7.4). Falls back to the
        raw value (free-text fields, or an option removed after answering)."""
        if value == OTHER_TOKEN:
            return "Other"
        for opt in field.get("options") or []:
            if isinstance(opt, dict) and opt.get("value") == value:
                lbl = opt.get("label")
                if isinstance(lbl, str) and lbl:
                    return lbl
        return value

    @staticmethod
    def _escape(text: str) -> str:
        """Escape for reportlab's mini-HTML Paragraph markup (it parses & < >)."""
        from xml.sax.saxutils import escape

        return escape(str(text))

    async def scrub(
        self,
        db: AsyncSession,
        *,
        doc: OnboardingPacketDocument,
        purge: bool = False,
    ) -> None:
        """RETAIN the non-sensitive answers on COMPLETION (§C.5); null on PURGE.

        Forms 2/4/5/6 are structured intake Lorenzo queries later, so on a
        successful completion (``purge=False``) a questionnaire keeps its answers
        in the existing column (unlike ``esign_pdf`` which nulls them). On a
        non-delivery terminal (``purge=True`` — revoke/expire/abandon/purge_pii)
        those answers ARE PII to destroy, so null them. Sensitive values are
        never in ``field_values`` (their ciphertext lives in the secret table,
        deleted by ``scrub_packet`` on purge), so retaining leaks no secret. The
        drawn signature (none for a questionnaire) is nulled at the packet level.
        """
        if purge:
            doc.field_values = {}


# Discovered + registered by the kinds package auto-loader (it reads this
# module-level ``HANDLER``). NO import from ``src.onboarding.kinds`` here so the
# handler module stays leaf and discovery is cycle-free.
HANDLER = QuestionnaireDocumentType()
