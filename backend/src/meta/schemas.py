"""Meta integration schemas."""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class MetaSyncRequest(BaseModel):
    page_id: str


class CompanyMetaDataResponse(BaseModel):
    id: int
    company_id: int
    page_id: str | None = None
    page_name: str | None = None
    followers_count: int | None = None
    likes_count: int | None = None
    category: str | None = None
    about: str | None = None
    website: str | None = None
    raw_json: dict | None = None
    instagram_id: str | None = None
    instagram_username: str | None = None
    instagram_followers: int | None = None
    instagram_media_count: int | None = None
    last_synced_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MetaConnectRequest(BaseModel):
    redirect_uri: str | None = None


class MetaCallbackRequest(BaseModel):
    code: str
    redirect_uri: str | None = None


class MetaCredentialResponse(BaseModel):
    id: int
    user_id: int
    is_active: bool
    scopes: str | None = None
    token_expiry: datetime | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MetaConnectionStatus(BaseModel):
    connected: bool
    scopes: str | None = None
    token_expiry: datetime | None = None
    pages: list[dict[str, Any]] = []


class MetaLeadCaptureResponse(BaseModel):
    id: int
    form_id: str
    leadgen_id: str
    page_id: str
    ad_id: str | None = None
    raw_data: dict | None = None
    lead_id: int | None = None
    processed: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MetaWebhookPayload(BaseModel):
    """Incoming Meta webhook for lead ads."""
    object: str
    entry: list[dict[str, Any]]
