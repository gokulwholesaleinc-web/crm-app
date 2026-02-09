"""Saved filter schemas."""

from typing import Optional
from pydantic import BaseModel
from datetime import datetime


class SavedFilterCreate(BaseModel):
    name: str
    entity_type: str
    filters: dict
    is_default: bool = False


class SavedFilterResponse(BaseModel):
    id: int
    name: str
    entity_type: str
    filters: str
    user_id: int
    is_default: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
