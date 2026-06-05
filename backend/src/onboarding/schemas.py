"""Pydantic schemas for onboarding templates (build-order §B).

Field-shape errors (bad enum, missing key, bad slug, bad prefill literal,
whitespace-only name, malformed service_tag, requires_esign without a
signature field) are caught by Pydantic → automatic 422. Geometry /
page-bounds / duplicate-id errors need the stored PDF and run in the
service (also → 422; see service.py).
"""

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Exactly four field kinds (build-order §G resolution #1).
FieldKind = Literal["signature", "date", "text", "address"]

# v3 document-kind discriminator (migration 052). Only ``esign_pdf`` templates
# carry placed-coordinate ``FieldDefinition``s; ``questionnaire`` and
# ``upload_request`` templates store their own per-kind field shapes (validated
# in ``src/onboarding/kinds/``). The list/detail response therefore passes
# ``field_definitions`` through as raw dicts and exposes ``kind`` so callers can
# discriminate — forcing every kind through the coordinate model 500s the list.
DocumentKind = Literal["esign_pdf", "questionnaire", "upload_request"]

# A service_tag is a real slug: lowercase alphanumeric segments joined by
# single hyphens — rejects bare/leading/trailing/doubled hyphens ('-', '--',
# '-x', 'x-'). ``null`` stays allowed (= a universal template); only a
# *provided* tag is validated. Hoisted to module scope so it compiles once.
_SERVICE_TAG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _normalized_service_tag(value: str | None) -> str | None:
    """Validate (do not silently rewrite) a service_tag slug.

    ``None`` passes through (universal template). A provided tag is stripped
    and must match ``^[a-z0-9-]+$`` — spaces, uppercase, and empty strings
    are rejected (422). We strip-then-check rather than lower-casing so a
    caller's intent is never silently mutated.
    """
    if value is None:
        return None
    stripped = value.strip()
    if not _SERVICE_TAG_RE.fullmatch(stripped):
        raise ValueError(
            "service_tag must be a slug of lowercase letters, digits, and "
            "hyphens (e.g. 'vendor-setup')"
        )
    return stripped


def _stripped_required_name(value: str) -> str:
    """Reject a whitespace-only name; return the stripped value.

    ``min_length=1`` alone accepts ``"   "`` (length 3), so strip first and
    require a non-empty result (422).
    """
    stripped = value.strip()
    if not stripped:
        raise ValueError("name must not be blank")
    return stripped

# prefill values are STORED in Phase 1; resolution (contact/company lookup)
# is Phase 2. ``contact.email`` is intentionally disallowed (§4.4).
PrefillSource = Literal["contact.name", "company.name"]


class FieldDefinition(BaseModel):
    """One placed field on the template PDF.

    Coords are PDF points, origin bottom-left, ``page`` 1-indexed (matches
    the picker; the stamper decrements at burn time).
    """

    id: str = Field(pattern=r"^[a-z0-9_]+$", min_length=1, max_length=64)
    kind: FieldKind
    label: str = Field(min_length=1, max_length=200)
    description: str | None = None
    required: bool = False
    prefill: PrefillSource | None = None
    page: int = Field(ge=1)
    x: float
    y: float
    w: float
    h: float


class TemplateCreate(BaseModel):
    """Create the metadata row + optional initial fields.

    ``kind`` discriminates the document type (default ``esign_pdf``). An
    ``esign_pdf`` template still cannot carry ``field_definitions`` at create —
    a PDF must exist first so coords can be bounds-validated (the service
    rejects initial fields for it). A ``questionnaire``/``upload_request``
    template has no PDF, so its fields are authored up front and validated by
    the per-kind handler in the service (raw ``dict`` passthrough — the handler,
    not this schema, owns each kind's field shape).
    """

    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    service_tag: str | None = Field(default=None, max_length=100)
    requires_esign: bool = False
    kind: DocumentKind = "esign_pdf"
    field_definitions: list[dict] | None = None

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        return _stripped_required_name(value)

    @field_validator("service_tag")
    @classmethod
    def _validate_service_tag(cls, value: str | None) -> str | None:
        return _normalized_service_tag(value)

    @model_validator(mode="after")
    def _no_esign_at_create(self) -> "TemplateCreate":
        """#10: a brand-new template has no fields yet, so it cannot satisfy
        the requires_esign ⇄ signature-field invariant. e-sign is enabled
        later via PATCH, once a signature field has been placed."""
        if self.requires_esign:
            raise ValueError(
                "Enable requires_esign after adding a signature field "
                "(a new template has no fields yet)."
            )
        return self


class TemplateUpdate(BaseModel):
    """Partial update (exclude_unset).

    ``field_definitions`` is a raw ``list[dict]`` passed straight to the
    template kind's handler (``get_handler(kind).validate_definitions``) in the
    service — the handler, not this schema, owns each kind's field shape
    (esign coords vs questionnaire questions vs upload fields), so forcing the
    coordinate ``FieldDefinition`` model here would 422 every questionnaire/
    upload save before the per-kind validator ever ran. The esign⇄signature
    reconciliation is row-aware and lives in
    ``service.update._assert_esign_signature_consistency`` (it can see the
    stored kind + the merged field set, which this schema cannot).
    """

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    service_tag: str | None = Field(default=None, max_length=100)
    requires_esign: bool | None = None
    field_definitions: list[dict] | None = None
    # Optimistic-lock token (C2): the pdf_version the editor was opened
    # against. When a PATCH carries field_definitions AND a pdf_version that
    # no longer matches the row, the PDF was re-uploaded out from under the
    # editor → the service raises StaleTemplateError → 409. ``None`` skips the
    # check (back-compat for metadata-only PATCHes).
    pdf_version: int | None = None

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str | None) -> str | None:
        return None if value is None else _stripped_required_name(value)

    @field_validator("service_tag")
    @classmethod
    def _validate_service_tag(cls, value: str | None) -> str | None:
        return _normalized_service_tag(value)


class StarterResponse(BaseModel):
    """A built-in starter template (``starter_definitions.STARTERS``).

    Surfaced by ``GET /templates/starters`` for the wizard's example picker and
    cloned into a real template by ``POST /templates/from-starter`` (keyed on
    ``key``). ``field_definitions`` are deliberately omitted — the picker only
    needs the identity + kind, and the clone reads the definition server-side.
    """

    key: str
    name: str
    description: str | None
    kind: DocumentKind
    service_tag: str | None


class TemplateResponse(BaseModel):
    """API view of a template.

    #3 SECURITY (C1): the raw storage ref (``pdf_path`` — an ``obj://`` R2
    key or an on-disk path) is NEVER exposed. Clients only need to know
    *whether* a PDF exists, so the response carries ``has_pdf: bool``
    (computed: ``pdf_path is not None``) instead. Build instances via
    :meth:`from_template` so the computation has a single source of truth.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    service_tag: str | None
    owner_id: int | None
    kind: DocumentKind
    has_pdf: bool
    pdf_version: int
    # Raw passthrough: the shape depends on ``kind`` (coordinate fields for
    # esign_pdf, questionnaire/upload fields otherwise) and is validated at
    # write time by the per-kind module, so the response does not re-validate
    # it against the coordinate ``FieldDefinition`` model.
    field_definitions: list[dict]
    requires_esign: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_template(cls, template) -> "TemplateResponse":
        """Serialize an ``OnboardingTemplate`` ORM row without leaking the
        storage ref. ``has_pdf`` is derived from ``pdf_path`` here so no
        route has to remember to redact it."""
        return cls(
            id=template.id,
            name=template.name,
            description=template.description,
            service_tag=template.service_tag,
            owner_id=template.owner_id,
            kind=template.kind,
            has_pdf=template.pdf_path is not None,
            pdf_version=template.pdf_version,
            field_definitions=template.field_definitions,
            requires_esign=template.requires_esign,
            is_active=template.is_active,
            created_at=template.created_at,
            updated_at=template.updated_at,
        )
