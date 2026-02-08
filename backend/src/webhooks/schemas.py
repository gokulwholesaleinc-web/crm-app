"""Pydantic schemas for webhooks."""

from datetime import datetime
from typing import Optional, List, Any, Dict
from pydantic import BaseModel, ConfigDict, HttpUrl


class WebhookCreate(BaseModel):
    name: str
    url: str
    events: List[str]
    secret: Optional[str] = None
    is_active: bool = True


class WebhookUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    events: Optional[List[str]] = None
    secret: Optional[str] = None
    is_active: Optional[bool] = None


class WebhookResponse(BaseModel):
    id: int
    name: str
    url: str
    events: List[str]
    secret: Optional[str] = None
    is_active: bool
    created_by_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WebhookDeliveryResponse(BaseModel):
    id: int
    webhook_id: int
    event_type: str
    payload: Optional[Dict[str, Any]] = None
    status: str
    response_code: Optional[int] = None
    error: Optional[str] = None
    attempted_at: datetime

    model_config = ConfigDict(from_attributes=True)
