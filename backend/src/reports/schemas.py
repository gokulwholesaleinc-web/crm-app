"""Pydantic schemas for custom reports."""

from datetime import datetime
from typing import Optional, Any, Dict, List
from pydantic import BaseModel, ConfigDict


class ReportDefinition(BaseModel):
    """Definition for executing a report."""
    entity_type: str
    metric: str = "count"  # count, sum, avg, min, max
    metric_field: Optional[str] = None
    group_by: Optional[str] = None
    date_group: Optional[str] = None  # day, week, month, quarter, year
    filters: Optional[Dict[str, Any]] = None
    chart_type: str = "bar"


class ReportDataPoint(BaseModel):
    """Single data point in report results."""
    label: str
    value: float


class ReportResult(BaseModel):
    """Result of executing a report."""
    entity_type: str
    metric: str
    metric_field: Optional[str] = None
    group_by: Optional[str] = None
    chart_type: str
    data: List[ReportDataPoint]
    total: Optional[float] = None


class SavedReportCreate(BaseModel):
    name: str
    description: Optional[str] = None
    entity_type: str
    filters: Optional[Dict[str, Any]] = None
    group_by: Optional[str] = None
    date_group: Optional[str] = None
    metric: str = "count"
    metric_field: Optional[str] = None
    chart_type: str = "bar"
    is_public: bool = False
    schedule: Optional[str] = None
    recipients: Optional[List[str]] = None


class SavedReportUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    filters: Optional[Dict[str, Any]] = None
    group_by: Optional[str] = None
    date_group: Optional[str] = None
    metric: Optional[str] = None
    metric_field: Optional[str] = None
    chart_type: Optional[str] = None
    is_public: Optional[bool] = None
    schedule: Optional[str] = None
    recipients: Optional[List[str]] = None


class SavedReportResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    entity_type: str
    filters: Optional[Dict[str, Any]] = None
    group_by: Optional[str] = None
    date_group: Optional[str] = None
    metric: str
    metric_field: Optional[str] = None
    chart_type: str
    created_by_id: int
    is_public: bool
    schedule: Optional[str] = None
    recipients: Optional[List[str]] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ReportTemplate(BaseModel):
    """Pre-built report template."""
    id: str
    name: str
    description: str
    entity_type: str
    metric: str
    metric_field: Optional[str] = None
    group_by: Optional[str] = None
    date_group: Optional[str] = None
    chart_type: str
    filters: Optional[Dict[str, Any]] = None


class AIReportGenerateRequest(BaseModel):
    """Request to generate a report from a natural language prompt."""
    prompt: str


class AIReportGenerateResponse(BaseModel):
    """Response from AI report generation."""
    definition: ReportDefinition
    result: ReportResult


class ScheduleUpdateRequest(BaseModel):
    """Request to update schedule on a saved report."""
    schedule: Optional[str] = None  # daily/weekly/monthly or null to clear
    recipients: Optional[List[str]] = None
