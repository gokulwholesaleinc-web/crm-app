"""Pydantic schemas for opportunities."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from src.core.schemas import TagBrief


class PipelineStageBase(BaseModel):
    name: str
    description: str | None = None
    order: int = 0
    color: str = "#6366f1"
    probability: int = 0
    is_won: bool = False
    is_lost: bool = False
    is_active: bool = True
    pipeline_type: str = "opportunity"


class PipelineStageCreate(PipelineStageBase):
    pass


class PipelineStageUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    order: int | None = None
    color: str | None = None
    probability: int | None = None
    is_won: bool | None = None
    is_lost: bool | None = None
    is_active: bool | None = None
    pipeline_type: str | None = None


class PipelineStageResponse(PipelineStageBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


class OpportunityBase(BaseModel):
    name: str
    description: str | None = None
    pipeline_stage_id: int
    amount: float | None = None
    currency: str = "USD"
    probability: int | None = None
    expected_close_date: date | None = None
    contact_id: int | None = None
    company_id: int | None = None
    source: str | None = None
    owner_id: int | None = None


class OpportunityCreate(OpportunityBase):
    tag_ids: list[int] | None = None


class OpportunityUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    pipeline_stage_id: int | None = None
    amount: float | None = None
    currency: str | None = None
    probability: int | None = None
    expected_close_date: date | None = None
    actual_close_date: date | None = None
    contact_id: int | None = None
    company_id: int | None = None
    source: str | None = None
    owner_id: int | None = None
    loss_reason: str | None = None
    loss_notes: str | None = None
    tag_ids: list[int] | None = None


class ContactBrief(BaseModel):
    id: int
    full_name: str

    model_config = ConfigDict(from_attributes=True)


class CompanyBrief(BaseModel):
    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)


class OpportunityResponse(OpportunityBase):
    id: int
    actual_close_date: date | None = None
    loss_reason: str | None = None
    loss_notes: str | None = None
    weighted_amount: float | None = None
    created_at: datetime
    updated_at: datetime
    pipeline_stage: PipelineStageResponse
    contact: ContactBrief | None = None
    company: CompanyBrief | None = None
    tags: list[TagBrief] = []

    model_config = ConfigDict(from_attributes=True)


class OpportunityListResponse(BaseModel):
    items: list[OpportunityResponse]
    total: int
    page: int
    page_size: int
    pages: int


# Kanban/Pipeline schemas
class KanbanOpportunity(BaseModel):
    id: int
    name: str
    amount: float | None
    currency: str
    weighted_amount: float | None
    expected_close_date: str | None
    contact_id: int | None
    contact_name: str | None
    company_id: int | None
    company_name: str | None
    owner_id: int | None


class KanbanStage(BaseModel):
    stage_id: int
    stage_name: str
    color: str
    probability: int
    is_won: bool
    is_lost: bool
    opportunities: list[KanbanOpportunity]
    total_amount: float
    total_weighted: float
    count: int


class KanbanResponse(BaseModel):
    stages: list[KanbanStage]


class MoveOpportunityRequest(BaseModel):
    new_stage_id: int


# Forecast schemas
class ForecastPeriod(BaseModel):
    month: str
    month_label: str
    best_case: float
    weighted: float
    commit: float
    opportunity_count: int


class ForecastTotals(BaseModel):
    best_case: float
    weighted: float
    commit: float


class ForecastResponse(BaseModel):
    periods: list[ForecastPeriod]
    totals: ForecastTotals
    currency: str


class PipelineSummaryStage(BaseModel):
    count: int
    value: float
    weighted: float


class PipelineSummaryResponse(BaseModel):
    total_opportunities: int
    total_value: float
    weighted_value: float
    currency: str
    by_stage: dict[str, PipelineSummaryStage]
