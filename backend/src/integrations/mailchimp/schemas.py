"""Pydantic schemas for Mailchimp connect/audience flows."""

from datetime import datetime

from pydantic import BaseModel, Field


class MailchimpConnectRequest(BaseModel):
    api_key: str = Field(..., min_length=10, max_length=128)


class MailchimpAudience(BaseModel):
    id: str
    name: str
    member_count: int = 0


class MailchimpStatus(BaseModel):
    connected: bool
    server_prefix: str | None = None
    account_email: str | None = None
    account_login_id: str | None = None
    default_audience_id: str | None = None
    default_audience_name: str | None = None
    connected_at: datetime | None = None


class MailchimpSetAudienceRequest(BaseModel):
    audience_id: str = Field(..., min_length=1, max_length=64)


class MailchimpStatsResponse(BaseModel):
    campaign_id: int
    mailchimp_campaign_id: str
    emails_sent: int
    opens: int
    unique_opens: int
    open_rate: float
    clicks: int
    unique_clicks: int
    click_rate: float
    bounces: int
    unsubscribes: int
