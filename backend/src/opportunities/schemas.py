"""Pydantic schemas for opportunities."""

from datetime import date, datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict
from src.core.schemas import TagBrief


class PipelineStageBase(BaseModel):
    name: str
    description: Optional[str] = None
    order: int = 0
    color: str = "#6366f1"
    probability: int = 0
    is_won: bool = False
    is_lost: bool = False
    is_active: bool = True


class PipelineStageCreate(PipelineStageBase):
    pass


class PipelineStageUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    order: Optional[int] = None
    color: Optional[str] = None
    probability: Optional[int] = None
    is_won: Optional[bool] = None
    is_lost: Optional[bool] = None
    is_active: Optional[bool] = None


class PipelineStageResponse(PipelineStageBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


class OpportunityBase(BaseModel):
    name: str
    description: Optional[str] = None
    pipeline_stage_id: int
    amount: Optional[float] = None
    currency: str = "USD"
    probability: Optional[int] = None
    expected_close_date: Optional[date] = None
    contact_id: Optional[int] = None
    company_id: Optional[int] = None
    source: Optional[str] = None
    owner_id: Optional[int] = None


class OpportunityCreate(OpportunityBase):
    tag_ids: Optional[List[int]] = None


class OpportunityUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    pipeline_stage_id: Optional[int] = None
    amount: Optional[float] = None
    currency: Optional[str] = None
    probability: Optional[int] = None
    expected_close_date: Optional[date] = None
    actual_close_date: Optional[date] = None
    contact_id: Optional[int] = None
    company_id: Optional[int] = None
    source: Optional[str] = None
    owner_id: Optional[int] = None
    loss_reason: Optional[str] = None
    loss_notes: Optional[str] = None
    tag_ids: Optional[List[int]] = None


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
    actual_close_date: Optional[date] = None
    loss_reason: Optional[str] = None
    loss_notes: Optional[str] = None
    weighted_amount: Optional[float] = None
    created_at: datetime
    updated_at: datetime
    pipeline_stage: PipelineStageResponse
    contact: Optional[ContactBrief] = None
    company: Optional[CompanyBrief] = None
    tags: List[TagBrief] = []

    model_config = ConfigDict(from_attributes=True)


class OpportunityListResponse(BaseModel):
    items: List[OpportunityResponse]
    total: int
    page: int
    page_size: int
    pages: int


# Kanban/Pipeline schemas
class KanbanOpportunity(BaseModel):
    id: int
    name: str
    amount: Optional[float]
    currency: str
    weighted_amount: Optional[float]
    expected_close_date: Optional[str]
    contact_name: Optional[str]
    company_name: Optional[str]
    owner_id: Optional[int]


class KanbanStage(BaseModel):
    stage_id: int
    stage_name: str
    color: str
    probability: int
    is_won: bool
    is_lost: bool
    opportunities: List[KanbanOpportunity]
    total_amount: float
    total_weighted: float
    count: int


class KanbanResponse(BaseModel):
    stages: List[KanbanStage]


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
    periods: List[ForecastPeriod]
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
    by_stage: Dict[str, PipelineSummaryStage]
