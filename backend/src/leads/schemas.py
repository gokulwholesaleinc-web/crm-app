"""Pydantic schemas for leads."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, model_validator

from src.core.schemas import TagBrief


class LeadSourceBase(BaseModel):
    name: str
    description: str | None = None
    is_active: bool = True


class LeadSourceCreate(LeadSourceBase):
    pass


class LeadSourceUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    is_active: bool | None = None


class LeadSourceResponse(LeadSourceBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


class LeadBase(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    mobile: str | None = None
    job_title: str | None = None
    company_name: str | None = None
    website: str | None = None
    industry: str | None = None
    source_id: int | None = None
    source_details: str | None = None
    address_line1: str | None = None
    address_line2: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    country: str | None = None
    description: str | None = None
    requirements: str | None = None
    budget_amount: float | None = None
    budget_currency: str = "USD"
    owner_id: int | None = None
    sales_code: str | None = None


class LeadCreate(LeadBase):
    status: str = "new"
    pipeline_stage_id: int | None = None
    tag_ids: list[int] | None = None

    @model_validator(mode="after")
    def require_name_or_company(self) -> "LeadCreate":
        has_name = bool((self.first_name or "").strip() or (self.last_name or "").strip())
        has_company = bool((self.company_name or "").strip())
        if not has_name and not has_company:
            raise ValueError("Either a name (first or last) or company_name is required")
        return self

    @model_validator(mode="after")
    def reject_direct_converted_status(self) -> "LeadCreate":
        # Mirrors the LeadService.update guard. The Convert flow is the
        # only legitimate path to status='converted' because it also
        # creates the Contact + Opportunity and stamps converted_*_id.
        # Without this validator the create endpoint was a back door
        # that produced the same orphan-converted rows the update guard
        # blocks.
        if self.status == "converted":
            raise ValueError(
                "Cannot create a lead with status='converted' — use the "
                "Convert action on a qualified lead so the contact and "
                "opportunity are created.",
            )
        return self


class LeadUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    mobile: str | None = None
    job_title: str | None = None
    company_name: str | None = None
    website: str | None = None
    industry: str | None = None
    source_id: int | None = None
    source_details: str | None = None
    status: str | None = None
    pipeline_stage_id: int | None = None
    address_line1: str | None = None
    address_line2: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    country: str | None = None
    description: str | None = None
    requirements: str | None = None
    budget_amount: float | None = None
    budget_currency: str | None = None
    owner_id: int | None = None
    sales_code: str | None = None
    tag_ids: list[int] | None = None


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
    score_factors: str | None = None
    pipeline_stage_id: int | None = None
    pipeline_stage: PipelineStageRef | None = None
    created_at: datetime
    updated_at: datetime
    source: LeadSourceResponse | None = None
    tags: list[TagBrief] = []
    converted_contact_id: int | None = None
    converted_opportunity_id: int | None = None

    model_config = ConfigDict(from_attributes=True)


class LeadListResponse(BaseModel):
    items: list[LeadResponse]
    total: int
    page: int
    page_size: int
    pages: int


# Conversion schemas
class LeadConvertToContactRequest(BaseModel):
    company_id: int | None = None
    create_company: bool = False


class LeadConvertToOpportunityRequest(BaseModel):
    pipeline_stage_id: int
    contact_id: int | None = None
    company_id: int | None = None


class LeadFullConversionRequest(BaseModel):
    pipeline_stage_id: int
    create_company: bool = True


class ConversionResponse(BaseModel):
    lead_id: int
    contact_id: int | None = None
    company_id: int | None = None
    opportunity_id: int | None = None
    message: str


# Lead Kanban / Pipeline schemas

class KanbanLead(BaseModel):
    id: int
    first_name: str | None = None
    last_name: str | None = None
    full_name: str
    email: str | None = None
    company_name: str | None = None
    score: int
    owner_id: int | None = None
    owner_name: str | None = None


class KanbanLeadStage(BaseModel):
    stage_id: int
    stage_name: str
    color: str
    probability: int
    is_won: bool
    is_lost: bool
    leads: list[KanbanLead]
    count: int


class LeadKanbanResponse(BaseModel):
    stages: list[KanbanLeadStage]
    message: str | None = None


class MoveLeadRequest(BaseModel):
    new_stage_id: int


class SendCampaignRequest(BaseModel):
    lead_ids: list[int]
    subject: str
    body_template: str  # Supports {{first_name}} placeholder
