"""Meta integration schemas."""
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict


class MetaSyncRequest(BaseModel):
    page_id: str


class CompanyMetaDataResponse(BaseModel):
    id: int
    company_id: int
    page_id: Optional[str] = None
    page_name: Optional[str] = None
    followers_count: Optional[int] = None
    likes_count: Optional[int] = None
    category: Optional[str] = None
    about: Optional[str] = None
    website: Optional[str] = None
    raw_json: Optional[dict] = None
    instagram_id: Optional[str] = None
    instagram_username: Optional[str] = None
    instagram_followers: Optional[int] = None
    instagram_media_count: Optional[int] = None
    last_synced_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MetaConnectRequest(BaseModel):
    redirect_uri: Optional[str] = None


class MetaCallbackRequest(BaseModel):
    code: str
    redirect_uri: Optional[str] = None


class MetaCredentialResponse(BaseModel):
    id: int
    user_id: int
    is_active: bool
    scopes: Optional[str] = None
    token_expiry: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MetaConnectionStatus(BaseModel):
    connected: bool
    scopes: Optional[str] = None
    token_expiry: Optional[datetime] = None
    pages: List[Dict[str, Any]] = []


class MetaLeadCaptureResponse(BaseModel):
    id: int
    form_id: str
    leadgen_id: str
    page_id: str
    ad_id: Optional[str] = None
    raw_data: Optional[dict] = None
    lead_id: Optional[int] = None
    processed: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MetaWebhookPayload(BaseModel):
    """Incoming Meta webhook for lead ads."""
    object: str
    entry: List[Dict[str, Any]]
