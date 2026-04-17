"""Email request/response schemas."""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr


class SendEmailRequest(BaseModel):
    """Request to send a single email."""
    to_email: EmailStr
    subject: str
    body: str
    from_email: EmailStr | None = None
    cc: str | None = None
    bcc: str | None = None
    entity_type: str | None = None
    entity_id: int | None = None


class SendTemplateEmailRequest(BaseModel):
    """Request to send an email using a template."""
    to_email: EmailStr
    template_id: int
    variables: dict = {}
    entity_type: str | None = None
    entity_id: int | None = None


class SendCampaignEmailRequest(BaseModel):
    """Request to send emails for a campaign."""
    campaign_id: int
    template_id: int
    variables: dict[str, str] | None = None


class EmailQueueResponse(BaseModel):
    """Email queue item response."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    to_email: str
    from_email: str | None = None
    subject: str
    body: str
    cc: str | None = None
    bcc: str | None = None
    status: str
    attempts: int
    error: str | None = None
    created_at: datetime
    sent_at: datetime | None = None
    opened_at: datetime | None = None
    clicked_at: datetime | None = None
    open_count: int = 0
    click_count: int = 0
    entity_type: str | None = None
    entity_id: int | None = None
    template_id: int | None = None
    campaign_id: int | None = None
    sent_by_id: int | None = None


class EmailListResponse(BaseModel):
    """Paginated list of emails."""
    items: list[EmailQueueResponse]
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
    cc: str | None = None
    bcc: str | None = None
    subject: str
    body_text: str | None = None
    body_html: str | None = None
    message_id: str | None = None
    in_reply_to: str | None = None
    attachments: Any | None = None
    entity_type: str | None = None
    entity_id: int | None = None
    received_at: datetime
    created_at: datetime


class EmailSettingsResponse(BaseModel):
    """Email settings response."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    daily_send_limit: int
    warmup_enabled: bool
    warmup_start_date: datetime | None = None
    warmup_target_daily: int


class EmailSettingsUpdate(BaseModel):
    """Email settings update request."""
    daily_send_limit: int | None = None
    warmup_enabled: bool | None = None
    warmup_start_date: str | None = None
    warmup_target_daily: int | None = None

    @property
    def parsed_warmup_date(self) -> date | None:
        """Parse warmup_start_date string to date object."""
        return date.fromisoformat(self.warmup_start_date) if self.warmup_start_date else None


class ThreadEmailItem(BaseModel):
    """A single email in a thread (inbound or outbound)."""
    id: int
    direction: str  # "inbound" or "outbound"
    from_email: str | None = None
    to_email: str
    cc: str | None = None
    subject: str
    body: str | None = None
    body_html: str | None = None
    timestamp: datetime
    status: str | None = None  # outbound only
    open_count: int | None = None  # outbound only
    attachments: Any | None = None  # inbound only
    thread_id: str | None = None


class ThreadResponse(BaseModel):
    """Paginated email thread combining inbound and outbound."""
    items: list[ThreadEmailItem]
    total: int
    page: int
    page_size: int
    pages: int
