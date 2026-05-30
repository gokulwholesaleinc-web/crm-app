"""Pydantic schemas for onboarding templates (build-order §B).

Field-shape errors (bad enum, missing key, bad slug, bad prefill literal)
are caught by Pydantic → automatic 422. Geometry / page-bounds / duplicate-id
errors need the stored PDF and run in the service (also → 422; see service.py).
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Exactly four field kinds (build-order §G resolution #1).
FieldKind = Literal["signature", "date", "text", "address"]

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
    """Create the metadata row. field_definitions cannot be set here — a PDF
    must exist first so coords can be bounds-validated."""

    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    service_tag: str | None = Field(default=None, max_length=100)
    requires_esign: bool = False


class TemplateUpdate(BaseModel):
    """Partial update (exclude_unset). field_definitions revalidates against
    the stored PDF in the service (422 on failure)."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    service_tag: str | None = Field(default=None, max_length=100)
    requires_esign: bool | None = None
    field_definitions: list[FieldDefinition] | None = None


class TemplateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    service_tag: str | None
    owner_id: int | None
    pdf_path: str | None
    pdf_version: int
    field_definitions: list[FieldDefinition]
    requires_esign: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime
