"""Email request/response schemas."""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, EmailStr


class SendEmailRequest(BaseModel):
    """Request to send a single email."""
    to_email: EmailStr
    subject: str
    body: str
    entity_type: Optional[str] = None
    entity_id: Optional[int] = None


class SendTemplateEmailRequest(BaseModel):
    """Request to send an email using a template."""
    to_email: EmailStr
    template_id: int
    variables: dict = {}
    entity_type: Optional[str] = None
    entity_id: Optional[int] = None


class SendCampaignEmailRequest(BaseModel):
    """Request to send emails for a campaign."""
    campaign_id: int


class EmailQueueResponse(BaseModel):
    """Email queue item response."""
    model_config = ConfigDict(from_attributes=True)

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
    open_count: int = 0
    click_count: int = 0
    entity_type: Optional[str] = None
    entity_id: Optional[int] = None
    template_id: Optional[int] = None
    campaign_id: Optional[int] = None
    sent_by_id: Optional[int] = None


class EmailListResponse(BaseModel):
    """Paginated list of emails."""
    items: List[EmailQueueResponse]
    total: int
    page: int
    page_size: int
    pages: int
