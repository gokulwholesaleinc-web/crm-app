"""Pydantic schemas for campaigns."""

from datetime import date, datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict


class CampaignBase(BaseModel):
    name: str
    description: Optional[str] = None
    campaign_type: str
    status: str = "planned"
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    budget_amount: Optional[float] = None
    actual_cost: Optional[float] = None
    budget_currency: str = "USD"
    target_audience: Optional[str] = None
    expected_revenue: Optional[float] = None
    expected_response: Optional[int] = None
    owner_id: Optional[int] = None


class CampaignCreate(CampaignBase):
    pass


class CampaignUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    campaign_type: Optional[str] = None
    status: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    budget_amount: Optional[float] = None
    actual_cost: Optional[float] = None
    budget_currency: Optional[str] = None
    target_audience: Optional[str] = None
    expected_revenue: Optional[float] = None
    expected_response: Optional[int] = None
    actual_revenue: Optional[float] = None
    num_sent: Optional[int] = None
    num_responses: Optional[int] = None
    num_converted: Optional[int] = None
    owner_id: Optional[int] = None


class CampaignResponse(CampaignBase):
    id: int
    actual_revenue: Optional[float] = None
    num_sent: int
    num_responses: int
    num_converted: int
    response_rate: Optional[float] = None
    conversion_rate: Optional[float] = None
    roi: Optional[float] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CampaignListResponse(BaseModel):
    items: List[CampaignResponse]
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
    status: Optional[str] = None
    sent_at: Optional[date] = None
    responded_at: Optional[date] = None
    converted_at: Optional[date] = None
    response_notes: Optional[str] = None


class CampaignMemberResponse(CampaignMemberBase):
    id: int
    sent_at: Optional[date] = None
    responded_at: Optional[date] = None
    converted_at: Optional[date] = None
    response_notes: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class AddMembersRequest(BaseModel):
    member_type: str
    member_ids: List[int]


class CampaignStats(BaseModel):
    total_members: int
    pending: int
    sent: int
    responded: int
    converted: int
    response_rate: Optional[float]
    conversion_rate: Optional[float]
