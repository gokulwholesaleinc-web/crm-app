"""Gmail integration schemas."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

GmailConnectionState = Literal["connected", "needs_reconnect", "disconnected"]


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


class GmailBackfillRequest(BaseModel):
    days: int = 365


class GmailBackfillStatusResponse(BaseModel):
    status: str
    processed_count: int
    total_count: int
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None


class GmailRelinkRequest(BaseModel):
    user_id: int | None = None
    dry_run: bool = False
    limit: int = 5000


class GmailRelinkResponse(BaseModel):
    scanned: int
    linked: int
    skipped: int
    dry_run: bool


class GmailAliasRefreshRequest(BaseModel):
    user_id: int | None = None
    force: bool = False


class GmailAliasRefreshResponse(BaseModel):
    refreshed: list[dict]
    skipped: int
    failed: list[dict]


class GmailRehydrateInlineImagesRequest(BaseModel):
    user_id: int | None = None
    dry_run: bool = False
    limit: int = 2_000


class GmailRehydrateInlineImagesResponse(BaseModel):
    scanned: int
    rehydrated: int
    skipped: int
    failed: int
    dry_run: bool


class GmailStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    # `state` is the load-bearing field for the UI:
    #   connected       — happy path
    #   needs_reconnect — was connected, Google revoked our refresh token
    #                     (typical for Testing-mode apps every ~7 days);
    #                     UI should show a Reconnect prompt and disable
    #                     compose/sync until the user re-OAuths.
    #   disconnected    — never connected, or user manually disconnected.
    # `connected` is kept for backwards compat with older clients but new
    # UI should branch on `state`.
    state: GmailConnectionState
    connected: bool
    email: str | None = None
    last_synced_at: datetime | None = None
    last_error: str | None = None
