"""Notification response schemas."""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict


class NotificationResponse(BaseModel):
    """Notification response."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    type: str
    title: str
    message: str
    entity_type: Optional[str] = None
    entity_id: Optional[int] = None
    is_read: bool
    created_at: datetime


class NotificationListResponse(BaseModel):
    """Paginated list of notifications."""
    items: List[NotificationResponse]
    total: int
    page: int
    page_size: int
    pages: int


class UnreadCountResponse(BaseModel):
    """Unread notification count."""
    count: int
