"""Pydantic schemas for saved filters."""

from datetime import datetime
from typing import Optional, Any, Dict
from pydantic import BaseModel, ConfigDict


class SavedFilterCreate(BaseModel):
    name: str
    entity_type: str
    filters: Dict[str, Any]
    is_default: bool = False


class SavedFilterUpdate(BaseModel):
    name: Optional[str] = None
    filters: Optional[Dict[str, Any]] = None
    is_default: Optional[bool] = None


class SavedFilterResponse(BaseModel):
    id: int
    name: str
    entity_type: str
    filters: Dict[str, Any]
    user_id: int
    is_default: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
