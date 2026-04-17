"""Pydantic schemas for saved filters."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class SavedFilterCreate(BaseModel):
    name: str
    entity_type: str
    filters: dict[str, Any]
    is_default: bool = False
    is_public: bool = False


class SavedFilterUpdate(BaseModel):
    name: str | None = None
    filters: dict[str, Any] | None = None
    is_default: bool | None = None
    is_public: bool | None = None


class SavedFilterResponse(BaseModel):
    id: int
    name: str
    entity_type: str
    filters: dict[str, Any]
    user_id: int
    is_default: bool
    is_public: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AggregateRequest(BaseModel):
    entity_type: str
    filters: dict[str, Any]
    metrics: list[str]


class AggregateResponse(BaseModel):
    count: int
    metrics: dict[str, Any]
    sample_entities: list[dict[str, Any]]
