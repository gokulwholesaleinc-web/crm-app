"""Email request/response schemas."""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

# Per-message attachment limits. 25 MB matches Gmail's user-facing send
# cap and is well under Resend's hard ceiling, so the same numbers
# apply regardless of which provider lights up at send time.
MAX_ATTACHMENT_SIZE_BYTES = 25 * 1024 * 1024
MAX_ATTACHMENTS_TOTAL_BYTES = 25 * 1024 * 1024
MAX_ATTACHMENT_COUNT = 10


class InlineAttachment(BaseModel):
    """A single attachment uploaded inline with the send request.

    `content_b64` is base64-encoded raw bytes. The router decodes once
    and passes through to the provider; we deliberately don't persist
    the bytes anywhere — only `{filename, content_type, size}` lands in
    `EmailQueue.attachments` for the email log.
    """

    filename: str = Field(..., min_length=1, max_length=255)
    content_type: str = Field(..., min_length=1, max_length=100)
    content_b64: str = Field(..., min_length=1)

    @field_validator("filename")
    @classmethod
    def _no_path_separators(cls, v: str) -> str:
        # Filenames are echoed back into MIME headers; reject anything
        # that looks like a path traversal or null byte.
        if "/" in v or "\\" in v or "\x00" in v:
            raise ValueError("filename must not contain path separators or null bytes")
        return v


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
    # When the user clicks Reply on a specific email we preserve threading by
    # pointing at its row id (outbound lives in EmailQueue, inbound in
    # InboundEmail — they share no id space, hence two fields).
    reply_to_email_id: int | None = None
    reply_to_inbound_id: int | None = None
    attachments: list[InlineAttachment] | None = None

    @model_validator(mode="after")
    def _validate_attachments(self) -> "SendEmailRequest":
        if not self.attachments:
            return self
        if len(self.attachments) > MAX_ATTACHMENT_COUNT:
            raise ValueError(
                f"too many attachments (max {MAX_ATTACHMENT_COUNT})"
            )
        # Base64 is ~4/3 the size of the raw bytes; check the *decoded*
        # size against the limit so we don't reject borderline payloads
        # for their wire bloat alone.
        import base64

        running_total = 0
        for att in self.attachments:
            try:
                raw = base64.b64decode(att.content_b64, validate=True)
            except Exception as exc:  # noqa: BLE001 — re-raised as ValueError below
                raise ValueError(
                    f"attachment '{att.filename}' is not valid base64"
                ) from exc
            if len(raw) == 0:
                raise ValueError(
                    f"attachment '{att.filename}' is empty"
                )
            if len(raw) > MAX_ATTACHMENT_SIZE_BYTES:
                raise ValueError(
                    f"attachment '{att.filename}' exceeds the "
                    f"{MAX_ATTACHMENT_SIZE_BYTES // (1024 * 1024)} MB limit"
                )
            running_total += len(raw)
            if running_total > MAX_ATTACHMENTS_TOTAL_BYTES:
                raise ValueError(
                    f"combined attachment size exceeds the "
                    f"{MAX_ATTACHMENTS_TOTAL_BYTES // (1024 * 1024)} MB limit"
                )
        return self


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
