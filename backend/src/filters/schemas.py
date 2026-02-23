"""Pydantic schemas for saved filters."""

from datetime import datetime
from typing import Optional, Any, Dict
from pydantic import BaseModel, ConfigDict


class SavedFilterCreate(BaseModel):
    name: str
    entity_type: str
    filters: Dict[str, Any]
    is_default: bool = False
    is_public: bool = False


class SavedFilterUpdate(BaseModel):
    name: Optional[str] = None
    filters: Optional[Dict[str, Any]] = None
    is_default: Optional[bool] = None
    is_public: Optional[bool] = None


class SavedFilterResponse(BaseModel):
    id: int
    name: str
    entity_type: str
    filters: Dict[str, Any]
    user_id: int
    is_default: bool
    is_public: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AggregateRequest(BaseModel):
    entity_type: str
    filters: Dict[str, Any]
    metrics: list[str]


class AggregateResponse(BaseModel):
    count: int
    metrics: Dict[str, Any]
    sample_entities: list[Dict[str, Any]]
