"""Pydantic schemas for onboarding template bundles ("saved packets").

The wizard's create body (an ordered list of clone/starter/blank items), the
list/detail responses (each member carries a backend-computed ``send_ready`` +
``send_reason`` so the frontend reads a flag and never re-derives readiness —
B5/D1), and the edit/reorder/add bodies.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.onboarding.schemas import (
    DocumentKind,
    _normalized_service_tag,
    _stripped_required_name,
)


class BundleWizardItem(BaseModel):
    """One document in the wizard's ordered list — a NEW template minted from a
    clone source, a built-in starter, or a blank spec. Each carries its own
    per-item template ``name`` (§4.4).

    ``source`` discriminates which extra fields are required:
      * ``clone``   → ``source_template_id`` (an active questionnaire/upload
        template; e-sign sources are refused 422).
      * ``starter`` → ``starter_key``.
      * ``blank``   → ``kind`` (+ optional description/service_tag/
        field_definitions, validated by the kind handler).
    """

    source: Literal["clone", "starter", "blank"]
    name: str = Field(min_length=1, max_length=255)
    # clone
    source_template_id: int | None = None
    # starter
    starter_key: str | None = None
    # blank
    kind: DocumentKind | None = None
    description: str | None = None
    service_tag: str | None = Field(default=None, max_length=100)
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
    def _check_source_fields(self) -> "BundleWizardItem":
        if self.source == "clone" and self.source_template_id is None:
            raise ValueError("clone items require source_template_id")
        if self.source == "starter" and not self.starter_key:
            raise ValueError("starter items require starter_key")
        if self.source == "blank" and self.kind is None:
            raise ValueError("blank items require kind")
        return self


class BundleCreate(BaseModel):
    """Wizard create body: a named, ordered set of documents (≥1 — §C3)."""

    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    items: list[BundleWizardItem] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        return _stripped_required_name(value)


class BundleUpdate(BaseModel):
    """Partial update: rename / re-describe / retire-restore a bundle."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    is_active: bool | None = None

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str | None) -> str | None:
        return None if value is None else _stripped_required_name(value)


class BundleReorder(BaseModel):
    """Reassign member order from a permutation of the bundle item ids."""

    ordered_item_ids: list[int] = Field(default_factory=list)


class BundleAddItem(BaseModel):
    """Append an existing template to a bundle."""

    template_id: int


class BundleMember(BaseModel):
    """One template reference inside a bundle (detail view).

    ``send_ready`` + ``send_reason`` are computed by the backend via
    ``template_send_status`` — the frontend reads the flag and never re-derives
    readiness (it can't: ``needs_pdf_copy`` is a backend handler property, not a
    serialized field — B5/D1).
    """

    model_config = ConfigDict(from_attributes=True)

    item_id: int
    template_id: int
    display_order: int
    name: str
    kind: DocumentKind
    requires_esign: bool
    is_active: bool
    has_pdf: bool
    send_ready: bool
    send_reason: str | None


class BundleSummary(BaseModel):
    """A saved packet in the list view (no members)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    is_active: bool
    item_count: int
    send_ready: bool
    created_at: datetime
    updated_at: datetime


class BundleDetail(BundleSummary):
    """A saved packet with its ordered members + per-member readiness."""

    members: list[BundleMember]
