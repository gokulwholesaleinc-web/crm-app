"""Pydantic schemas for custom reports."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ReportDefinition(BaseModel):
    """Definition for executing a report."""
    entity_type: str
    metric: str = "count"  # count, sum, avg, min, max
    metric_field: str | None = None
    group_by: str | None = None
    date_group: str | None = None  # day, week, month, quarter, year
    filters: dict[str, Any] | None = None
    chart_type: str = "bar"


class ReportDataPoint(BaseModel):
    """Single data point in report results."""
    label: str
    value: float


class ReportResult(BaseModel):
    """Result of executing a report."""
    entity_type: str
    metric: str
    metric_field: str | None = None
    group_by: str | None = None
    chart_type: str
    data: list[ReportDataPoint]
    total: float | None = None


class SavedReportCreate(BaseModel):
    name: str
    description: str | None = None
    entity_type: str
    filters: dict[str, Any] | None = None
    group_by: str | None = None
    date_group: str | None = None
    metric: str = "count"
    metric_field: str | None = None
    chart_type: str = "bar"
    is_public: bool = False
    schedule: str | None = None
    recipients: list[str] | None = None


class SavedReportUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    filters: dict[str, Any] | None = None
    group_by: str | None = None
    date_group: str | None = None
    metric: str | None = None
    metric_field: str | None = None
    chart_type: str | None = None
    is_public: bool | None = None
    schedule: str | None = None
    recipients: list[str] | None = None


class SavedReportResponse(BaseModel):
    id: int
    name: str
    description: str | None = None
    entity_type: str
    filters: dict[str, Any] | None = None
    group_by: str | None = None
    date_group: str | None = None
    metric: str
    metric_field: str | None = None
    chart_type: str
    created_by_id: int
    is_public: bool
    schedule: str | None = None
    recipients: list[str] | None = None
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
    metric_field: str | None = None
    group_by: str | None = None
    date_group: str | None = None
    chart_type: str
    filters: dict[str, Any] | None = None


class AIReportGenerateRequest(BaseModel):
    """Request to generate a report from a natural language prompt."""
    prompt: str


class AIReportGenerateResponse(BaseModel):
    """Response from AI report generation."""
    definition: ReportDefinition
    result: ReportResult


class ScheduleUpdateRequest(BaseModel):
    """Request to update schedule on a saved report."""
    schedule: str | None = None  # daily/weekly/monthly or null to clear
    recipients: list[str] | None = None
