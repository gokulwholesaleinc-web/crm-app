"""Pydantic schemas for Google Calendar integration."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

CalendarConnectionState = Literal["connected", "needs_reconnect", "disconnected"]


class GoogleCalendarConnect(BaseModel):
    """Request to initiate OAuth2 flow."""
    redirect_uri: str | None = None


class GoogleCalendarCallback(BaseModel):
    """OAuth2 callback data."""
    code: str
    state: str | None = None
    redirect_uri: str | None = None


class GoogleCalendarCredentialResponse(BaseModel):
    """Response showing connection status (never exposes tokens)."""
    id: int
    user_id: int
    calendar_id: str
    is_active: bool
    last_synced_at: datetime | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class GoogleCalendarEventCreate(BaseModel):
    """Create a Google Calendar event from a CRM activity."""
    activity_id: int


class CalendarSyncStatus(BaseModel):
    """Status of calendar sync for a user.

    `state` distinguishes the three UX situations the frontend renders
    differently:

      - **connected** — credential row exists with is_active=True.
      - **needs_reconnect** — credential row exists but is_active was
        flipped to False because Google rejected our refresh token
        (400 invalid_grant). User needs to re-authorize; their stored
        sync history is preserved.
      - **disconnected** — no credential row. Manual disconnect path,
        or never connected.

    `connected` remains for backwards compatibility (frontend still
    branches on it for the basic Sync/Connect choice).
    """
    state: CalendarConnectionState = "disconnected"
    connected: bool
    calendar_id: str | None = None
    last_synced_at: datetime | None = None
    synced_events_count: int = 0
    last_error: str | None = None
