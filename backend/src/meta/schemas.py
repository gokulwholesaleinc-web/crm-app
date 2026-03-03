"""Meta integration schemas."""
from datetime import datetime
from typing import Optional
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
    last_synced_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
