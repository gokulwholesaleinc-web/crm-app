"""Pydantic schemas for campaigns."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class CampaignBase(BaseModel):
    name: str
    description: str | None = None
    campaign_type: str
    status: str = "planned"
    start_date: date | None = None
    end_date: date | None = None
    budget_amount: float | None = None
    actual_cost: float | None = None
    budget_currency: str = "USD"
    target_audience: str | None = None
    expected_revenue: float | None = None
    expected_response: int | None = None
    owner_id: int | None = None
    send_via: Literal["resend", "mailchimp"] = "resend"


class CampaignCreate(CampaignBase):
    pass


class CampaignUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    campaign_type: str | None = None
    status: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    budget_amount: float | None = None
    actual_cost: float | None = None
    budget_currency: str | None = None
    target_audience: str | None = None
    expected_revenue: float | None = None
    expected_response: int | None = None
    actual_revenue: float | None = None
    num_sent: int | None = None
    num_responses: int | None = None
    num_converted: int | None = None
    owner_id: int | None = None
    send_via: Literal["resend", "mailchimp"] | None = None


class CampaignResponse(CampaignBase):
    id: int
    actual_revenue: float | None = None
    num_sent: int
    num_responses: int
    num_converted: int
    current_step: int = 0
    next_step_at: datetime | None = None
    is_executing: bool = False
    mailchimp_campaign_id: str | None = None
    response_rate: float | None = None
    conversion_rate: float | None = None
    roi: float | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CampaignListResponse(BaseModel):
    items: list[CampaignResponse]
    total: int
    page: int
    page_size: int
    pages: int


# Campaign Member schemas
class CampaignMemberBase(BaseModel):
    campaign_id: int
    member_type: str  # contact, lead
    member_id: int
    status: str = "pending"


class CampaignMemberCreate(CampaignMemberBase):
    pass


class CampaignMemberUpdate(BaseModel):
    status: str | None = None
    sent_at: datetime | None = None
    responded_at: datetime | None = None
    converted_at: datetime | None = None
    response_notes: str | None = None


class CampaignMemberResponse(CampaignMemberBase):
    id: int
    sent_at: datetime | None = None
    responded_at: datetime | None = None
    converted_at: datetime | None = None
    response_notes: str | None = None

    model_config = ConfigDict(from_attributes=True)


class AddMembersRequest(BaseModel):
    member_type: str
    member_ids: list[int]


class CreateFromImportRequest(BaseModel):
    name: str
    member_ids: list[int]
    member_type: Literal["contacts", "leads"] = "contacts"
    template_id: int | None = None
    schedule_start: datetime | None = None
    delay_days: int = 1


class CampaignStats(BaseModel):
    total_members: int
    pending: int
    sent: int
    responded: int
    converted: int
    response_rate: float | None
    conversion_rate: float | None


# Campaign Analytics schemas
class StepAnalytics(BaseModel):
    step_order: int
    template_name: str
    sent: int
    opened: int
    clicked: int
    failed: int
    open_rate: float
    click_rate: float


class CampaignAnalytics(BaseModel):
    campaign_id: int
    total_sent: int
    total_opened: int
    total_clicked: int
    total_failed: int
    open_rate: float
    click_rate: float
    steps: list[StepAnalytics]


# Email Template schemas
class EmailTemplateCreate(BaseModel):
    name: str
    subject_template: str
    body_template: str
    category: str | None = None


class EmailTemplateUpdate(BaseModel):
    name: str | None = None
    subject_template: str | None = None
    body_template: str | None = None
    category: str | None = None


class EmailTemplateResponse(BaseModel):
    id: int
    name: str
    subject_template: str
    body_template: str
    category: str | None = None
    created_by_id: int | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# Email Campaign Step schemas
class EmailCampaignStepCreate(BaseModel):
    template_id: int
    delay_days: int = 0
    step_order: int


class EmailCampaignStepUpdate(BaseModel):
    template_id: int | None = None
    delay_days: int | None = None
    step_order: int | None = None


class EmailCampaignStepResponse(BaseModel):
    id: int
    campaign_id: int
    template_id: int
    delay_days: int
    step_order: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EmailCampaignStepReorderRequest(BaseModel):
    """Atomic reorder: caller submits the full list of step IDs in the
    desired order. Server assigns step_order = index + 1.

    The endpoint validates that the submitted set matches the campaign's
    current step set exactly — no extras, no missing — so a stale client
    can't accidentally drop a step that another user just added.
    """

    step_ids: list[int]
