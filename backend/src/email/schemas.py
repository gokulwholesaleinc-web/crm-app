"""Email request/response schemas."""

from datetime import date, datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, EmailStr


class SendEmailRequest(BaseModel):
    """Request to send a single email."""
    to_email: EmailStr
    subject: str
    body: str
    from_email: Optional[EmailStr] = None
    cc: Optional[str] = None
    bcc: Optional[str] = None
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
    template_id: int
    variables: Optional[Dict[str, str]] = None


class EmailQueueResponse(BaseModel):
    """Email queue item response."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    to_email: str
    from_email: Optional[str] = None
    subject: str
    body: str
    cc: Optional[str] = None
    bcc: Optional[str] = None
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


class InboundEmailResponse(BaseModel):
    """Inbound email response."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    resend_email_id: str
    from_email: str
    to_email: str
    cc: Optional[str] = None
    bcc: Optional[str] = None
    subject: str
    body_text: Optional[str] = None
    body_html: Optional[str] = None
    message_id: Optional[str] = None
    in_reply_to: Optional[str] = None
    attachments: Optional[Any] = None
    entity_type: Optional[str] = None
    entity_id: Optional[int] = None
    received_at: datetime
    created_at: datetime


class EmailSettingsResponse(BaseModel):
    """Email settings response."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    daily_send_limit: int
    warmup_enabled: bool
    warmup_start_date: Optional[datetime] = None
    warmup_target_daily: int


class EmailSettingsUpdate(BaseModel):
    """Email settings update request."""
    daily_send_limit: Optional[int] = None
    warmup_enabled: Optional[bool] = None
    warmup_start_date: Optional[str] = None
    warmup_target_daily: Optional[int] = None

    @property
    def parsed_warmup_date(self) -> Optional[date]:
        """Parse warmup_start_date string to date object."""
        return date.fromisoformat(self.warmup_start_date) if self.warmup_start_date else None


class ThreadEmailItem(BaseModel):
    """A single email in a thread (inbound or outbound)."""
    id: int
    direction: str  # "inbound" or "outbound"
    from_email: Optional[str] = None
    to_email: str
    cc: Optional[str] = None
    subject: str
    body: Optional[str] = None
    body_html: Optional[str] = None
    timestamp: datetime
    status: Optional[str] = None  # outbound only
    open_count: Optional[int] = None  # outbound only
    attachments: Optional[Any] = None  # inbound only
    thread_id: Optional[str] = None


class ThreadResponse(BaseModel):
    """Paginated email thread combining inbound and outbound."""
    items: List[ThreadEmailItem]
    total: int
    page: int
    page_size: int
    pages: int
