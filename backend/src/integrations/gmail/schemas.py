"""Gmail integration schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class GmailConnectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    scopes: list[str]
    is_active: bool
    last_synced_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class GmailAuthorizeResponse(BaseModel):
    auth_url: str


class GmailCallbackRequest(BaseModel):
    code: str
    state: str


class GmailSendRequest(BaseModel):
    sent_via: str | None = None


class GmailStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    connected: bool
    email: str | None = None
    last_synced_at: datetime | None = None
    last_error: str | None = None
