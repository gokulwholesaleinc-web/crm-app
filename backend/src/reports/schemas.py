"""Report schemas."""

from typing import Optional, List, Any
from pydantic import BaseModel
from datetime import datetime


class ReportDefinition(BaseModel):
    entity_type: str
    filters: Optional[dict] = None
    group_by: Optional[str] = None
    date_group: Optional[str] = None
    metric: str = "count"
    metric_field: Optional[str] = None


class ReportDataPoint(BaseModel):
    label: str
    value: float


class ReportResult(BaseModel):
    data: List[ReportDataPoint]
    total: float
    entity_type: str
    metric: str
    group_by: Optional[str] = None


class SavedReportCreate(BaseModel):
    name: str
    description: Optional[str] = None
    entity_type: str
    filters: Optional[dict] = None
    group_by: Optional[str] = None
    date_group: Optional[str] = None
    metric: str = "count"
    metric_field: Optional[str] = None
    chart_type: str = "bar"
    is_public: bool = False


class SavedReportUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    filters: Optional[dict] = None
    group_by: Optional[str] = None
    date_group: Optional[str] = None
    metric: Optional[str] = None
    metric_field: Optional[str] = None
    chart_type: Optional[str] = None
    is_public: Optional[bool] = None


class SavedReportResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    entity_type: str
    filters: Optional[str] = None
    group_by: Optional[str] = None
    date_group: Optional[str] = None
    metric: str
    metric_field: Optional[str] = None
    chart_type: str
    created_by_id: int
    is_public: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ReportTemplate(BaseModel):
    id: str
    name: str
    description: str
    entity_type: str
    group_by: Optional[str] = None
    metric: str = "count"
    metric_field: Optional[str] = None
    chart_type: str = "bar"
