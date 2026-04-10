"""Pydantic schemas for leads."""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, EmailStr, ConfigDict
from src.core.schemas import TagBrief


class LeadSourceBase(BaseModel):
    name: str
    description: Optional[str] = None
    is_active: bool = True


class LeadSourceCreate(LeadSourceBase):
    pass


class LeadSourceResponse(LeadSourceBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


class LeadBase(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    mobile: Optional[str] = None
    job_title: Optional[str] = None
    company_name: Optional[str] = None
    website: Optional[str] = None
    industry: Optional[str] = None
    source_id: Optional[int] = None
    source_details: Optional[str] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None
    description: Optional[str] = None
    requirements: Optional[str] = None
    budget_amount: Optional[float] = None
    budget_currency: str = "USD"
    owner_id: Optional[int] = None
    sales_code: Optional[str] = None


class LeadCreate(LeadBase):
    status: str = "new"
    pipeline_stage_id: Optional[int] = None
    tag_ids: Optional[List[int]] = None


class LeadUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    mobile: Optional[str] = None
    job_title: Optional[str] = None
    company_name: Optional[str] = None
    website: Optional[str] = None
    industry: Optional[str] = None
    source_id: Optional[int] = None
    source_details: Optional[str] = None
    status: Optional[str] = None
    pipeline_stage_id: Optional[int] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None
    description: Optional[str] = None
    requirements: Optional[str] = None
    budget_amount: Optional[float] = None
    budget_currency: Optional[str] = None
    owner_id: Optional[int] = None
    sales_code: Optional[str] = None
    tag_ids: Optional[List[int]] = None


class PipelineStageRef(BaseModel):
    id: int
    name: str
    order: int = 0
    color: str = "#6366f1"
    probability: int = 0
    is_won: bool = False
    is_lost: bool = False

    model_config = ConfigDict(from_attributes=True)


class LeadResponse(LeadBase):
    id: int
    full_name: str
    status: str
    score: int
    score_factors: Optional[str] = None
    pipeline_stage_id: Optional[int] = None
    pipeline_stage: Optional[PipelineStageRef] = None
    created_at: datetime
    updated_at: datetime
    source: Optional[LeadSourceResponse] = None
    tags: List[TagBrief] = []
    converted_contact_id: Optional[int] = None
    converted_opportunity_id: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class LeadListResponse(BaseModel):
    items: List[LeadResponse]
    total: int
    page: int
    page_size: int
    pages: int


# Conversion schemas
class LeadConvertToContactRequest(BaseModel):
    company_id: Optional[int] = None
    create_company: bool = False


class LeadConvertToOpportunityRequest(BaseModel):
    pipeline_stage_id: int
    contact_id: Optional[int] = None
    company_id: Optional[int] = None


class LeadFullConversionRequest(BaseModel):
    pipeline_stage_id: int
    create_company: bool = True


class ConversionResponse(BaseModel):
    lead_id: int
    contact_id: Optional[int] = None
    company_id: Optional[int] = None
    opportunity_id: Optional[int] = None
    message: str


# =============================================================================
# Lead Kanban / Pipeline schemas
# =============================================================================

class KanbanLead(BaseModel):
    id: int
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    full_name: str
    email: Optional[str] = None
    company_name: Optional[str] = None
    score: int
    owner_id: Optional[int] = None


class KanbanLeadStage(BaseModel):
    stage_id: int
    stage_name: str
    color: str
    probability: int
    is_won: bool
    is_lost: bool
    leads: List[KanbanLead]
    count: int


class LeadKanbanResponse(BaseModel):
    stages: List[KanbanLeadStage]
    message: Optional[str] = None


class MoveLeadRequest(BaseModel):
    new_stage_id: int


class SendCampaignRequest(BaseModel):
    lead_ids: List[int]
    subject: str
    body_template: str  # Supports {{first_name}} placeholder
