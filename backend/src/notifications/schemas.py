"""Notification response schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NotificationResponse(BaseModel):
    """Notification response."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    type: str
    title: str
    message: str
    entity_type: str | None = None
    entity_id: int | None = None
    # Resolved by the router via `core.entity_links.fill_entity_labels`.
    # `entity_label` is a display-friendly name (e.g. "Acme Corp"); `entity_link`
    # is the frontend URL prefix + id (e.g. "/companies/42"). Both are None
    # for unroutable types or when the underlying row is missing.
    entity_label: str | None = None
    entity_link: str | None = None
    is_read: bool
    created_at: datetime


class NotificationListResponse(BaseModel):
    """Paginated list of notifications."""
    items: list[NotificationResponse]
    total: int
    page: int
    page_size: int
    pages: int


class UnreadCountResponse(BaseModel):
    """Unread notification count."""
    count: int
