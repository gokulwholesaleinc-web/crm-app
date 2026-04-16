"""Pydantic schemas for the Gmail integration API."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr


class GmailConnectionResponse(BaseModel):
    """Shape returned to the frontend when describing a user's Gmail connection."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    scopes: list[str]
    is_active: bool
    last_synced_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class GmailAuthorizeResponse(BaseModel):
    """Response from /api/integrations/gmail/authorize — caller redirects to auth_url."""

    auth_url: str


class GmailCallbackRequest(BaseModel):
    """Body of POST /api/integrations/gmail/callback."""

    code: str
    state: str


class GmailSendRequest(BaseModel):
    """Optional Gmail-specific routing hint for outbound sends.

    sent_via=None lets the email service decide based on whether a GmailConnection
    exists for the sending user; sent_via='resend' forces Resend; sent_via='gmail'
    forces Gmail (and errors if no connection).
    """

    sent_via: Optional[str] = None


class GmailStatusResponse(BaseModel):
    """Lightweight endpoint for the UI to poll connection health."""

    model_config = ConfigDict(from_attributes=True)

    connected: bool
    email: Optional[str] = None
    last_synced_at: Optional[datetime] = None
    last_error: Optional[str] = None
