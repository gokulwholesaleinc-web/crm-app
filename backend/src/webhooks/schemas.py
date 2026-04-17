"""Pydantic schemas for webhooks."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class WebhookCreate(BaseModel):
    name: str
    url: str
    events: list[str]
    secret: str | None = None
    is_active: bool = True


class WebhookUpdate(BaseModel):
    name: str | None = None
    url: str | None = None
    events: list[str] | None = None
    secret: str | None = None
    is_active: bool | None = None


class WebhookResponse(BaseModel):
    id: int
    name: str
    url: str
    events: list[str]
    secret: str | None = None
    is_active: bool
    created_by_id: int | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WebhookDeliveryResponse(BaseModel):
    id: int
    webhook_id: int
    event_type: str
    payload: dict[str, Any] | None = None
    status: str
    response_code: int | None = None
    error: str | None = None
    attempted_at: datetime

    model_config = ConfigDict(from_attributes=True)
