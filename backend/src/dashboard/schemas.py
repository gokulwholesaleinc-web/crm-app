"""Pydantic schemas for dashboard."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class NumberCardData(BaseModel):
    id: str
    label: str
    value: Any  # Can be int, float
    format: str | None = None  # currency, percentage, number
    icon: str | None = None
    color: str = "#6366f1"
    change: float | None = None  # Percentage change


class ChartDataPoint(BaseModel):
    label: str
    value: Any
    color: str | None = None


class ChartData(BaseModel):
    type: str  # bar, line, pie, funnel, area
    title: str
    data: list[ChartDataPoint]


class DashboardResponse(BaseModel):
    number_cards: list[NumberCardData]
    charts: list[ChartData]


class NumberCardConfig(BaseModel):
    id: int
    name: str
    label: str
    description: str | None = None
    config: str  # JSON string
    color: str = "#6366f1"
    icon: str | None = None
    is_active: bool = True
    order: int = 0
    show_percentage_change: bool = False

    model_config = ConfigDict(from_attributes=True)


class ChartConfig(BaseModel):
    id: int
    name: str
    label: str
    description: str | None = None
    chart_type: str
    config: str  # JSON string
    is_active: bool = True
    order: int = 0
    width: str = "half"

    model_config = ConfigDict(from_attributes=True)


# Sales Funnel schemas
class FunnelStage(BaseModel):
    stage: str
    count: int
    color: str | None = None


class FunnelConversion(BaseModel):
    from_stage: str
    to_stage: str
    rate: float


class SalesFunnelResponse(BaseModel):
    stages: list[FunnelStage]
    conversions: list[FunnelConversion]
    avg_days_in_stage: dict[str, float | None]


# Report Widget schemas
class ReportWidgetCreate(BaseModel):
    report_id: int
    position: int = 0
    width: str = "half"


class ReportWidgetUpdate(BaseModel):
    position: int | None = None
    width: str | None = None
    is_visible: bool | None = None


class ReportWidgetResponse(BaseModel):
    id: int
    user_id: int
    report_id: int
    report_name: str
    report_chart_type: str
    position: int
    width: str
    is_visible: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
