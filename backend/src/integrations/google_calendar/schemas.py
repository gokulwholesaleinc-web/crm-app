"""Pydantic schemas for Google Calendar integration."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class GoogleCalendarConnect(BaseModel):
    """Request to initiate OAuth2 flow."""
    redirect_uri: Optional[str] = None


class GoogleCalendarCallback(BaseModel):
    """OAuth2 callback data."""
    code: str
    state: Optional[str] = None


class GoogleCalendarCredentialResponse(BaseModel):
    """Response showing connection status (never exposes tokens)."""
    id: int
    user_id: int
    calendar_id: str
    is_active: bool
    last_synced_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class GoogleCalendarEventCreate(BaseModel):
    """Create a Google Calendar event from a CRM activity."""
    activity_id: int


class CalendarSyncStatus(BaseModel):
    """Status of calendar sync for a user."""
    connected: bool
    calendar_id: Optional[str] = None
    last_synced_at: Optional[datetime] = None
    synced_events_count: int = 0
