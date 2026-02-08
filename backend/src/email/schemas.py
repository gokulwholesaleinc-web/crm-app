"""Pydantic schemas for email operations."""

from datetime import datetime
from typing import Optional, List, Dict
from pydantic import BaseModel, ConfigDict, EmailStr


class SendEmailRequest(BaseModel):
    to_email: EmailStr
    subject: str
    body: str
    entity_type: Optional[str] = None
    entity_id: Optional[int] = None


class SendTemplateEmailRequest(BaseModel):
    to_email: EmailStr
    template_id: int
    variables: Optional[Dict[str, str]] = None
    entity_type: Optional[str] = None
    entity_id: Optional[int] = None


class SendCampaignEmailRequest(BaseModel):
    campaign_id: int
    template_id: int
    variables: Optional[Dict[str, str]] = None


class EmailQueueResponse(BaseModel):
    id: int
    to_email: str
    subject: str
    body: str
    status: str
    attempts: int
    error: Optional[str] = None
    created_at: datetime
    sent_at: Optional[datetime] = None
    opened_at: Optional[datetime] = None
    clicked_at: Optional[datetime] = None
    open_count: int
    click_count: int
    entity_type: Optional[str] = None
    entity_id: Optional[int] = None
    template_id: Optional[int] = None
    campaign_id: Optional[int] = None
    sent_by_id: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class EmailListResponse(BaseModel):
    items: List[EmailQueueResponse]
    total: int
    page: int
    page_size: int
    pages: int
