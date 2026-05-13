"""Pydantic schemas for Mailchimp connect/audience flows."""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


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
    blocked_audience_ids: list[str] = Field(default_factory=list)
    connected_at: datetime | None = None


class MailchimpSetAudienceRequest(BaseModel):
    audience_id: str = Field(..., min_length=1, max_length=64)


class MailchimpBlockedAudiencesRequest(BaseModel):
    """Full replacement of the blocked-audience list — admin sends the
    desired post-state, server stores it. Empty list = no blocks.

    Per-item ``max_length=64`` mirrors the DB column ``VARCHAR(64)[]``
    and matches ``MailchimpSetAudienceRequest.audience_id`` so callers
    get a clean 422 instead of a DB-level 500.
    """

    blocked_audience_ids: list[str] = Field(
        default_factory=list,
        max_length=128,
    )

    @field_validator("blocked_audience_ids")
    @classmethod
    def _validate_items(cls, v: list[str]) -> list[str]:
        for item in v:
            if not isinstance(item, str):
                raise ValueError("Each audience id must be a string")
            if len(item) > 64:
                raise ValueError(
                    f"Audience id exceeds 64 chars: {item[:32]!r}..."
                )
        return v


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
