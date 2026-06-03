"""DocumentType plugin registry for onboarding document kinds (v3, §B).

A STRATEGY REGISTRY keyed on the packet document's ``kind`` discriminator —
NOT ORM single-table inheritance (which would force a Base remap of the live
``OnboardingPacketDocument`` and risk the running core's dense concurrency
invariants). Each handler owns its author-time validation, fill-time value
coercion, completion required-check, completion artifact production, and scrub.
The lifecycle/security CORE stays kind-agnostic and dispatches through
``KIND_HANDLERS[doc.kind]``.

Load-bearing discipline (§B.1): no code OUTSIDE a handler method may index a
kind-specific key of ``field_definitions`` / ``field_values`` — that is what
dissolves the PDF-baked P0s at the ROOT.

Anti-silent-no-op defense (§B.2): a NON-optional ``Protocol`` (no default no-op
base class) + an IMPORT-TIME presence self-test. A handler missing any member
fails at process start, not in production — killing the "a new kind silently
no-ops a security/completion step" failure class that bred P0-6/P0-8. The
presence check verifies member PRESENCE only (``Protocol``/``runtime_checkable``
cannot verify signature/arity); the kind-parametrized real-PG test matrix is the
real contract guard.
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.onboarding.models import OnboardingPacket, OnboardingPacketDocument


@runtime_checkable
class DocumentType(Protocol):
    """The plugin contract every onboarding document kind must satisfy."""

    kind: str  # "esign_pdf" | "questionnaire" | "upload_request"
    needs_pdf_copy: bool  # copy the template PDF into the packet doc at create
    produces_signature: bool  # esign only
    records_view_via_stream: bool  # esign records on /pdf; others on /viewed

    def validate_definitions(
        self, defs: list[dict], *, pdf_bytes: bytes | None
    ) -> None:
        """Author-time field validation; branches BEFORE any PDF read (P0-9).

        MUST reuse the shared ``ALLOWED_PREFILL`` so ``email``/PII can never be
        made prefillable.
        """
        ...

    def validate_value(
        self, field: dict, value: object
    ) -> tuple[object, bytes | None]:
        """Fill-time per-field wire AND format check.

        Returns ``(plaintext_for_jsonb, ciphertext)``: ``email``→EmailStr /
        ``url``→AnyUrl coercion (422 on garbage, not just non-empty); a
        sensitive text field → ``(None, ciphertext)``; non-sensitive →
        ``(value, None)``.
        """
        ...

    def required_satisfied(
        self,
        field: dict,
        values: dict,
        uploads: list | None,
        secrets: dict | None,
    ) -> bool:
        """Completion gate; kind-aware (counts uploads / list non-emptiness /
        conditional Other write-in). Dissolves P0-1/P0-8."""
        ...

    async def produce_artifact(
        self,
        db: AsyncSession,
        *,
        doc: OnboardingPacketDocument,
        packet: OnboardingPacket,
        signature_png: bytes | None,
        dry_run: bool = False,
    ) -> bytes | None:
        """Phase-B output bytes. ``dry_run=True`` checks producibility WITHOUT
        writing the Attachment (used by Phase-A validation). ``None`` ⇒ no
        summary artifact needed. Dissolves P0-1/P0-3."""
        ...

    async def scrub(
        self, db: AsyncSession, *, doc: OnboardingPacketDocument
    ) -> None:
        """Null answers + delete uploads (via ``AttachmentService.delete_attachment``)
        + delete secret rows. Dissolves P0-6."""
        ...


KIND_HANDLERS: dict[str, DocumentType] = {}

# Every registered handler must carry these members (presence guard).
_REQUIRED_ATTRS = ("kind", "needs_pdf_copy", "produces_signature",
                   "records_view_via_stream")
_REQUIRED_METHODS = ("validate_definitions", "validate_value",
                     "required_satisfied", "produce_artifact", "scrub")


def _assert_implements(handler: object) -> None:
    """Fail LOUDLY at registration if a handler omits any Protocol member."""
    missing = [
        m for m in (*_REQUIRED_ATTRS, *_REQUIRED_METHODS) if not hasattr(handler, m)
    ]
    if missing:
        raise TypeError(
            f"DocumentType handler {type(handler).__name__!r} is missing required "
            f"member(s): {', '.join(missing)}"
        )
    not_callable = [m for m in _REQUIRED_METHODS if not callable(getattr(handler, m))]
    if not_callable:
        raise TypeError(
            f"DocumentType handler {type(handler).__name__!r} member(s) not "
            f"callable: {', '.join(not_callable)}"
        )
    kind = getattr(handler, "kind", None)
    if not isinstance(kind, str) or not kind:
        raise TypeError(
            f"DocumentType handler {type(handler).__name__!r} .kind must be a "
            "non-empty str"
        )


def register(handler: DocumentType) -> DocumentType:
    """Register ``handler`` under its ``kind`` after the presence self-test."""
    _assert_implements(handler)
    KIND_HANDLERS[handler.kind] = handler
    return handler


def get_handler(kind: str) -> DocumentType:
    """Return the handler for ``kind`` or raise ``KeyError`` (an unregistered
    kind is a hard error, never a silent no-op)."""
    try:
        return KIND_HANDLERS[kind]
    except KeyError as exc:
        raise KeyError(
            f"No onboarding DocumentType registered for kind {kind!r}"
        ) from exc


# --- auto-discover + register every handler module in this package ----------
# Each handler module exposes a module-level ``HANDLER`` instance and imports
# NOTHING from this package (leaf-only) — so discovery is cycle-free and a NEW
# KIND IS ADDED BY DROPPING IN A FILE, with no edit to this registry index (two
# parallel handler branches therefore never collide here). ``register`` runs the
# presence self-test on each discovered handler, so a malformed kind still fails
# loudly at import.
def _autoregister() -> None:
    for module_info in pkgutil.iter_modules(__path__):
        module = importlib.import_module(f"{__name__}.{module_info.name}")
        handler = getattr(module, "HANDLER", None)
        if handler is not None:
            register(handler)


_autoregister()
