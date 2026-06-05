"""Service layer for onboarding templates (build-order §C).

CRUD + PDF upload (with versioning) + save-time field-definition validation.
The library is GLOBAL (team-shared, §5.1) so list/get apply no owner filter;
write paths (upload/patch/retire) gate on ``check_ownership`` in the router.

Field-definition validation raises ``FieldDefinitionError`` which the router
maps to **422**. It deliberately does NOT subclass ``ValueError`` so it can
never be silently downgraded to a 400 by ``value_error_as_400`` (§G #2).
"""

from __future__ import annotations

import io
import uuid
from typing import TYPE_CHECKING

from pypdf import PdfReader
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.onboarding import storage
from src.onboarding.kinds import KIND_HANDLERS, get_handler
from src.onboarding.models import OnboardingTemplate
from src.onboarding.schemas import _normalized_service_tag

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

# Bounded backstop for the auto-suffix savepoint loop (V3-2) — far above any
# realistic number of same-named copies; a higher count means a misconfigured
# caller, not a legitimate collision, so fail loudly rather than spin.
_MAX_COPY_SUFFIX_TRIES = 50
# Leave headroom under the name's 255-char cap for the " (copy NNN)" suffix.
_COPY_BASE_MAX_LEN = 240


class FieldDefinitionError(Exception):
    """Save-time field_definitions validation failure → HTTP 422.

    Intentionally NOT a ``ValueError`` so a stray ``value_error_as_400``
    can't silently turn the mandated 422 into a 400.
    """


class DuplicateTemplateNameError(Exception):
    """Template ``name`` collides with ``uq_onboarding_templates_name`` → HTTP
    422 (S1). NOT a ``ValueError`` so it can't be downgraded to a 400.
    """


class StaleTemplateError(Exception):
    """Optimistic-lock failure (C2, finding #2) → HTTP 409.

    Raised when a PATCH carries field_definitions tied to a stale
    ``pdf_version`` — the PDF was re-uploaded after the editor opened, so
    the submitted coords reference a document that no longer exists. NOT a
    ``ValueError`` so it can't be downgraded to a 400.
    """


class RetiredTemplateError(Exception):
    """Edit attempted on a retired (is_active=False) template → HTTP 409
    (finding #11). Restore the template before editing. NOT a ``ValueError``.
    """


class PdfRejectedError(ValueError):
    """Upload-time PDF rejection (encrypted / rotated / unreadable / empty)
    → HTTP 400 (findings #4, #8). A ``ValueError`` subclass so the existing
    ``value_error_as_400`` wrapper in the router maps it to 400 uniformly.
    """


class StorageWriteError(Exception):
    """Persisting the uploaded PDF to the storage backend (R2/disk) failed
    → HTTP 503. NOT a ``ValueError`` so a write outage is never mislabelled
    as a client-side 400.
    """


def template_send_status(
    *, is_active: bool, kind: str, pdf_path: str | None, field_count: int
) -> tuple[bool, str | None]:
    """Single source of truth for "can this template become a packet document
    right now?" — the readiness check every send/select site shares (audit B2 +
    V3-3).

    Takes the MINIMAL fields (not a full ORM row) so a column-projection query
    can reuse it. Returns ``(ready, reason)`` where ``reason`` is a standalone,
    user-facing sentence when not ready, else ``None``. The missing-template
    check (the row doesn't exist at all) stays caller-side — this function only
    judges a row that was found.

    Not-ready when: retired / unknown-kind / an e-sign template without a PDF /
    a FORM kind (questionnaire, upload_request) with zero fields. The last guard
    (D2) stops the wizard's "blank document" shells — and any empty form — from
    being sent to a client as an empty form/manifest; a blank form is surfaced as
    "needs setup" exactly like a blank e-sign (§4.7).

    Reused at all three readiness sites:
      * ``packet_service._load_active_templates`` — RAISES on ``not ready``.
      * ``selection_service._assert_templates_active`` — RAISES on ``not ready``.
      * the bundle detail serializer — RETURNS the flag + reason per member.
    """
    if not is_active:
        return False, "This template has been retired and can no longer be sent."
    if kind not in KIND_HANDLERS:
        return False, "This template has an unknown kind and cannot be sent."
    if KIND_HANDLERS[kind].needs_pdf_copy and not pdf_path:
        return False, "This e-sign template has no PDF uploaded yet."
    # Form kinds (no PDF copy) need at least one authored field, else the client
    # would receive an empty form / blank upload manifest.
    if not KIND_HANDLERS[kind].needs_pdf_copy and field_count == 0:
        return False, "This form has no questions or fields yet."
    return True, None


class OnboardingTemplateService:
    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _build_template(
        *,
        current_user: User,
        name: str,
        description: str | None,
        service_tag: str | None,
        requires_esign: bool,
        kind: str,
        field_definitions: list[dict] | None,
    ) -> OnboardingTemplate:
        """Construct (but do NOT persist) a validated ``OnboardingTemplate``.

        Everything ``create()`` does BEFORE the flush — with NO DB I/O — so the
        batch wizard and clone paths reuse 100% of the validation + owner-setting
        instead of hand-constructing ORM rows (audit B1). The caller owns
        ``add``/``flush``/IntegrityError mapping.

        esign_pdf places coordinate fields only AFTER a PDF is uploaded (coords
        bounds-check against it), so it cannot carry initial field_definitions;
        questionnaire/upload_request author their fields up front and validate
        them now via the per-kind handler (no PDF needed — P0-9).
        """
        defs = field_definitions or []
        if kind == "esign_pdf":
            if defs:
                raise FieldDefinitionError(
                    "esign_pdf templates place fields after uploading a PDF; "
                    "create the template, upload a PDF, then add fields."
                )
        elif defs:
            # KeyError is impossible here — ``kind`` is a DocumentKind literal
            # validated by the schema, so the handler always exists. Store the
            # handler's RETURN (the validated/normalized list), not the raw input.
            defs = list(get_handler(kind).validate_definitions(defs, pdf_bytes=None))
        # AuditableMixin does NOT auto-populate created_by_id; set it (and
        # owner_id) explicitly so check_ownership and the audit trail work.
        return OnboardingTemplate(
            name=name,
            description=description,
            service_tag=service_tag,
            requires_esign=requires_esign,
            kind=kind,
            owner_id=current_user.id,
            created_by_id=current_user.id,
            field_definitions=defs,
        )

    async def create(
        self,
        *,
        current_user: User,
        name: str,
        description: str | None = None,
        service_tag: str | None = None,
        requires_esign: bool = False,
        kind: str = "esign_pdf",
        field_definitions: list[dict] | None = None,
    ) -> OnboardingTemplate:
        template = self._build_template(
            current_user=current_user,
            name=name,
            description=description,
            service_tag=service_tag,
            requires_esign=requires_esign,
            kind=kind,
            field_definitions=field_definitions,
        )
        self.db.add(template)
        try:
            await self.db.flush()
        except IntegrityError as exc:
            # uq_onboarding_templates_name collision (S1). Roll back the failed
            # flush so the session is usable, then surface a clean 422 instead
            # of a raw 500 (the router maps DuplicateTemplateNameError → 422).
            await self.db.rollback()
            raise DuplicateTemplateNameError(
                "A template with this name already exists."
            ) from exc
        await self.db.refresh(template)
        return template

    # ----------------------------------------------------------------------
    # Clone + from-starter (§4.3) — build-then-persist, reusing _build_template.
    # ----------------------------------------------------------------------
    @staticmethod
    def clone_build_kwargs(source: OnboardingTemplate) -> dict:
        """``_build_template`` kwargs (sans ``name``/``current_user``) that clone
        a source template's definition. Cloning is questionnaire/upload ONLY,
        from an ACTIVE source (§4.3); e-sign is refused (its PDF + placed coords
        are template-specific) and a retired source is refused.

        Copies ``description``, ``kind``, ``requires_esign``, the deep-copied
        ``field_definitions``, and the ``service_tag`` re-run through the slug
        validator (D4). Raises ``FieldDefinitionError`` (→ 422) on refusal.
        """
        if not source.is_active:
            raise FieldDefinitionError(
                "Cannot clone a retired template; restore it first."
            )
        if source.kind == "esign_pdf":
            raise FieldDefinitionError(
                "E-sign templates can't be cloned — their PDF and placed fields "
                "are template-specific. Create a new e-sign template instead."
            )
        return {
            "description": source.description,
            "service_tag": _normalized_service_tag(source.service_tag),
            "requires_esign": source.requires_esign,
            "kind": source.kind,
            "field_definitions": list(source.field_definitions or []),
        }

    @staticmethod
    def starter_build_kwargs(spec: dict) -> dict:
        """``_build_template`` kwargs (sans ``name``/``current_user``) for a
        built-in starter spec. service_tag re-run through the slug validator (D4);
        field_definitions deep-copied so the module-level STARTERS stay pristine.
        """
        return {
            "description": spec["description"],
            "service_tag": _normalized_service_tag(spec["service_tag"]),
            "requires_esign": False,
            "kind": spec["kind"],
            "field_definitions": list(spec["field_definitions"]),
        }

    async def clone_template(
        self,
        source: OnboardingTemplate,
        *,
        current_user: User,
        name: str | None = None,
    ) -> OnboardingTemplate:
        """Clone an active questionnaire/upload template into a fresh one.

        Explicit ``name`` collision → 422 (no silent rename); omitted ``name`` →
        auto-suffix ``"{source} (copy[, N])"``.
        """
        kwargs = self.clone_build_kwargs(source)

        def build(target_name: str) -> OnboardingTemplate:
            return self._build_template(
                current_user=current_user, name=target_name, **kwargs
            )

        return await self._persist_with_name_policy(
            build, explicit_name=name, base_name=source.name
        )

    async def create_from_starter(
        self,
        spec: dict,
        *,
        current_user: User,
        name: str | None = None,
    ) -> OnboardingTemplate:
        """Instantiate a built-in starter (resolved spec) into a fresh template.

        Explicit ``name`` collision → 422; omitted ``name`` → auto-suffix off the
        starter name (the seeded starter usually already owns the bare name).
        """
        kwargs = self.starter_build_kwargs(spec)

        def build(target_name: str) -> OnboardingTemplate:
            return self._build_template(
                current_user=current_user, name=target_name, **kwargs
            )

        return await self._persist_with_name_policy(
            build, explicit_name=name, base_name=spec["name"]
        )

    async def _persist_with_name_policy(
        self,
        build: Callable[[str], OnboardingTemplate],
        *,
        explicit_name: str | None,
        base_name: str,
    ) -> OnboardingTemplate:
        """Persist a built template under the clone/from-starter name policy.

        Explicit name → ``create()``'s plain rollback-and-give-up (a collision is
        a hard 422). Omitted name → ``_insert_with_auto_suffix`` (pre-query +
        SAVEPOINT backstop, V3-2).
        """
        if explicit_name is not None:
            template = build(explicit_name)
            self.db.add(template)
            try:
                await self.db.flush()
            except IntegrityError as exc:
                await self.db.rollback()
                raise DuplicateTemplateNameError(
                    "A template with this name already exists."
                ) from exc
            await self.db.refresh(template)
            return template
        return await self._insert_with_auto_suffix(build, base_name=base_name)

    async def _insert_with_auto_suffix(
        self,
        build: Callable[[str], OnboardingTemplate],
        *,
        base_name: str,
    ) -> OnboardingTemplate:
        """Insert with an auto-suffixed ``"{base} (copy[, N])"`` name (V3-2).

        A failed ``flush()`` aborts the whole Postgres transaction, so a naive
        bump-and-re-flush is impossible. Instead: pre-query the existing
        ``"{base} (copy%"`` names and pick the first free suffix in one shot, then
        insert inside a ``SAVEPOINT`` (``begin_nested``) as a BOUNDED terminal
        backstop — a same-instant collision rolls back only that savepoint and
        bumps once more (bounded, never infinite). The savepoint's race-safety is
        review-asserted; tests cover the same-session pre-query path (honest per
        §3/B3 — a real race isn't reproduced on the single-threaded harness).
        """
        base = base_name[:_COPY_BASE_MAX_LEN]
        # Escape LIKE wildcards in the base so a source named e.g. "50% off" or
        # "Form_1" doesn't over-match unrelated rows (cosmetic — the unique
        # constraint + SAVEPOINT backstop are the real guards, but over-matching
        # would pick a higher suffix than necessary).
        like_base = (
            base.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        )
        taken = set(
            (
                await self.db.execute(
                    select(OnboardingTemplate.name).where(
                        OnboardingTemplate.name.like(f"{like_base} (copy%", escape="\\")
                    )
                )
            )
            .scalars()
            .all()
        )
        tries = 0
        for candidate in self._copy_name_candidates(base):
            if candidate in taken:
                continue
            tries += 1
            if tries > _MAX_COPY_SUFFIX_TRIES:
                raise DuplicateTemplateNameError(
                    "Could not find a free copy name; rename the source first."
                )
            template = build(candidate)
            try:
                async with self.db.begin_nested():
                    self.db.add(template)
                    await self.db.flush()
            except IntegrityError:
                # A same-instant insert took this exact name: only the savepoint
                # rolled back (the outer transaction is intact), so record it and
                # bump to the next candidate.
                taken.add(candidate)
                continue
            await self.db.refresh(template)
            return template
        # The candidate generator is infinite, so this is unreachable; kept so
        # the function has a definite return for type-checkers.
        raise DuplicateTemplateNameError("Could not generate a copy name.")

    @staticmethod
    def _copy_name_candidates(base: str) -> Iterator[str]:
        """Yield ``"{base} (copy)"``, ``"{base} (copy 2)"``, … indefinitely."""
        yield f"{base} (copy)"
        n = 2
        while True:
            yield f"{base} (copy {n})"
            n += 1

    async def list(
        self,
        *,
        service_tag: str | None = None,
        include_inactive: bool = False,
    ) -> list[OnboardingTemplate]:
        """Global team library — no owner filter (§5.1)."""
        query = select(OnboardingTemplate)
        if service_tag is not None:
            query = query.where(OnboardingTemplate.service_tag == service_tag)
        if not include_inactive:
            query = query.where(OnboardingTemplate.is_active.is_(True))
        query = query.order_by(OnboardingTemplate.created_at.desc())
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get(self, template_id: int) -> OnboardingTemplate | None:
        result = await self.db.execute(
            select(OnboardingTemplate).where(OnboardingTemplate.id == template_id)
        )
        return result.scalar_one_or_none()

    async def update(
        self,
        template: OnboardingTemplate,
        *,
        current_user: User,
        field_definitions: list[dict] | None = None,
        pdf_version: int | None = None,
        **fields,
    ) -> OnboardingTemplate:
        """Apply a partial update. ``fields`` are already exclude_unset.

        ``field_definitions`` (if provided) is validated against the stored
        PDF and reassigned as a fresh list (JSONB has no in-place mutation
        tracking, but a whole-list reassignment is tracked, §G #7).

        Guards (in order):
          * #11 retired templates reject all edits (409).
          * C2 a field-definitions PATCH carrying a stale ``pdf_version``
            (the PDF was re-uploaded since the editor opened) → 409.
          * #10 the resulting (requires_esign, field set) must be consistent:
            an esign template needs ≥1 signature field. Evaluated against the
            *merged* state so an esign-on / fields-unchanged PATCH is caught.
        """
        # #11: a retired template is read-only until restored.
        if not template.is_active:
            raise RetiredTemplateError(
                "Template is retired; restore it before editing."
            )

        # C2: optimistic lock — only meaningful when this PATCH ships fields.
        if (
            field_definitions is not None
            and pdf_version is not None
            and pdf_version != template.pdf_version
        ):
            raise StaleTemplateError(
                "This template's PDF was replaced; reload before saving fields."
            )

        for key, value in fields.items():
            setattr(template, key, value)
        if field_definitions is not None:
            # Dispatch author-time validation on the template's kind: esign reads
            # the stored PDF (coords/bounds); questionnaire/upload branch BEFORE
            # any PDF read (P0-9). Both kinds reuse the shared ALLOWED_PREFILL
            # inside the handler so email/PII can never be made prefillable.
            handler = get_handler(template.kind)
            pdf_bytes = (
                await self._read_pdf_bytes(template)
                if handler.needs_pdf_copy
                else None
            )
            # Persist the handler's RETURN (the validated/normalized list) — for
            # esign that is the model-normalized shape (declared keys, coerced
            # types), not the raw request dict, so storage matches validation.
            template.field_definitions = list(
                handler.validate_definitions(field_definitions, pdf_bytes=pdf_bytes)
            )

        # #10: reconcile esign ⇄ signature-field consistency against the
        # merged state (the requires_esign just set above + the fields now on
        # the row). The stamper demands a PNG whenever any signature field
        # exists; we mirror the converse here — an esign template with zero
        # signature fields could never collect a signature, so reject it.
        self._assert_esign_signature_consistency(template)

        template.updated_by_id = current_user.id
        await self.db.flush()
        await self.db.refresh(template)
        return template

    @staticmethod
    def _assert_esign_signature_consistency(template: OnboardingTemplate) -> None:
        """#10: a requires_esign template must carry ≥1 signature field.

        Raises ``FieldDefinitionError`` (→ 422). Evaluated on the merged row
        state so it fires for an esign-on PATCH that leaves the (sig-less)
        fields untouched, not just for single-payload combos caught by the
        schema validator.
        """
        if not template.requires_esign:
            return
        fields = template.field_definitions or []
        if not any(
            (f.get("kind") if isinstance(f, dict) else getattr(f, "kind", None))
            == "signature"
            for f in fields
        ):
            raise FieldDefinitionError(
                "requires_esign templates must define at least one "
                "signature field before saving."
            )

    async def retire(
        self, template: OnboardingTemplate, *, current_user: User
    ) -> OnboardingTemplate:
        template.is_active = False
        template.updated_by_id = current_user.id
        await self.db.flush()
        await self.db.refresh(template)
        return template

    async def restore(
        self, template: OnboardingTemplate, *, current_user: User
    ) -> OnboardingTemplate:
        """Un-retire a template so it can be edited/used again (#11)."""
        template.is_active = True
        template.updated_by_id = current_user.id
        await self.db.flush()
        await self.db.refresh(template)
        return template

    async def upload_pdf(
        self,
        template: OnboardingTemplate,
        *,
        current_user: User,
        content: bytes,
    ) -> OnboardingTemplate:
        """Store a new PDF for the template.

        A re-upload bumps ``pdf_version``, writes a NEW versioned object
        (the old one is left in place — staff-managed, few templates), and
        CLEARS ``field_definitions`` because the old coords are meaningless
        against a new PDF (build-order §C re-upload semantics).
        """
        # #11: a retired template is read-only until restored.
        if not template.is_active:
            raise RetiredTemplateError(
                "Template is retired; restore it before editing."
            )
        # Validate the bytes (empty / unreadable / encrypted / rotated)
        # BEFORE writing anything, so a rejected upload leaves no orphan.
        self._validate_uploaded_pdf(content)

        is_reupload = template.pdf_path is not None
        next_version = (template.pdf_version + 1) if is_reupload else template.pdf_version
        # Clean, feature-namespaced key — NOT generate_object_key, whose
        # "uploads/" prefix would double under the storage disk root.
        key = f"onboarding_templates/{template.id}/{uuid.uuid4().hex}.pdf"
        # Map a storage-backend failure (e.g. R2 ClientError surfaced as a
        # RuntimeError) to a 503, not a 500. NOTE (orphan risk): the write
        # succeeds on the object store but a later self.db.flush() failure
        # would leave the object un-referenced; Phase 1 accepts this (few
        # staff-managed templates, no automatic GC). A reaper is deferred.
        try:
            ref = await storage.write(key, content, "application/pdf")
        except RuntimeError as exc:
            raise StorageWriteError(
                "Could not store the uploaded PDF (storage unavailable)."
            ) from exc

        template.pdf_path = ref
        template.pdf_version = next_version
        if is_reupload:
            # Old coords are meaningless against the new PDF. Clearing the
            # fields would leave a requires_esign template with zero signature
            # fields (violating #10), so reset requires_esign too — staff
            # re-enable it after re-placing a signature field on the new PDF.
            template.field_definitions = []
            template.requires_esign = False
        template.updated_by_id = current_user.id
        await self.db.flush()
        await self.db.refresh(template)
        return template

    async def get_pdf_bytes(self, template: OnboardingTemplate) -> bytes:
        """Read the stored PDF bytes (caller wraps in a Response)."""
        if not template.pdf_path:
            raise FileNotFoundError("Template has no PDF")
        return await storage.read_bytes(template.pdf_path)

    async def _read_pdf_bytes(self, template: OnboardingTemplate) -> bytes:
        if not template.pdf_path:
            raise FieldDefinitionError(
                "Upload a PDF before defining fields on this template."
            )
        return await storage.read_bytes(template.pdf_path)

    @staticmethod
    def _validate_uploaded_pdf(content: bytes) -> None:
        """Reject empty / unreadable / encrypted / rotated PDFs at upload.

        All four raise ``PdfRejectedError`` (a ``ValueError`` subclass) → 400.

        * #4 encrypted: ``PdfReader`` does NOT raise on an encrypted file;
          only page access does. We check ``reader.is_encrypted`` explicitly.
        * #8 rotated: the editor's pdf.js viewport already applies page
          rotation while the backend bounds-checks against the raw mediabox,
          so a non-zero ``/Rotate`` would misplace every field. Fail closed
          (``page.rotation`` resolves inherited rotation too); full rotation
          support is deferred.
        """
        if not content:
            raise PdfRejectedError("Uploaded PDF is empty")
        try:
            reader = PdfReader(io.BytesIO(content))
        except Exception as exc:  # pypdf raises a variety of parse errors
            raise PdfRejectedError("Uploaded file is not a readable PDF") from exc

        if reader.is_encrypted:
            raise PdfRejectedError(
                "Encrypted/password-protected PDFs are not supported."
            )

        for page in reader.pages:
            # ``page.rotation`` normalizes to a multiple of 90 in [0, 360) and
            # accounts for rotation inherited from the page tree.
            if page.rotation % 360 != 0:
                raise PdfRejectedError(
                    "Rotated PDF pages aren't supported yet; please upload an "
                    "unrotated PDF."
                )

    # NOTE: the esign coords/bounds/uniqueness/prefill validation extracted to
    # ``onboarding.kinds.esign_pdf.validate_esign_definitions`` (v3 §B); this
    # method now dispatches through ``get_handler(template.kind)`` in ``update``.
