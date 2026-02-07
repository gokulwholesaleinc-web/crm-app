"""Pydantic schemas for dashboard."""

from typing import Optional, List, Any, Dict
from pydantic import BaseModel, ConfigDict


class NumberCardData(BaseModel):
    id: str
    label: str
    value: Any  # Can be int, float
    format: Optional[str] = None  # currency, percentage, number
    icon: Optional[str] = None
    color: str = "#6366f1"
    change: Optional[float] = None  # Percentage change


class ChartDataPoint(BaseModel):
    label: str
    value: Any
    color: Optional[str] = None


class ChartData(BaseModel):
    type: str  # bar, line, pie, funnel, area
    title: str
    data: List[ChartDataPoint]


class DashboardResponse(BaseModel):
    number_cards: List[NumberCardData]
    charts: List[ChartData]


class NumberCardConfig(BaseModel):
    id: int
    name: str
    label: str
    description: Optional[str] = None
    config: str  # JSON string
    color: str = "#6366f1"
    icon: Optional[str] = None
    is_active: bool = True
    order: int = 0
    show_percentage_change: bool = False

    model_config = ConfigDict(from_attributes=True)


class ChartConfig(BaseModel):
    id: int
    name: str
    label: str
    description: Optional[str] = None
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
    color: Optional[str] = None


class FunnelConversion(BaseModel):
    from_stage: str
    to_stage: str
    rate: float


class SalesFunnelResponse(BaseModel):
    stages: List[FunnelStage]
    conversions: List[FunnelConversion]
    avg_days_in_stage: Dict[str, Optional[float]]
