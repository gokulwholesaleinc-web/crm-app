"""Gmail integration schemas."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class GmailConnectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    scopes: list[str]
    is_active: bool
    last_synced_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class GmailAuthorizeResponse(BaseModel):
    auth_url: str


class GmailCallbackRequest(BaseModel):
    code: str
    state: str


class GmailSendRequest(BaseModel):
    sent_via: Optional[str] = None


class GmailStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    connected: bool
    email: Optional[str] = None
    last_synced_at: Optional[datetime] = None
    last_error: Optional[str] = None
