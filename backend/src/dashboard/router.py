"""Dashboard API routes."""

from typing import Annotated, List
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_db
from src.auth.models import User
from src.auth.dependencies import get_current_active_user
from src.dashboard.schemas import (
    NumberCardData,
    ChartData,
    ChartDataPoint,
    DashboardResponse,
)
from src.dashboard.number_cards import NumberCardGenerator
from src.dashboard.charts import ChartDataGenerator

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardResponse)
async def get_dashboard(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Get full dashboard data including KPIs and charts."""
    # Get KPIs
    kpi_generator = NumberCardGenerator(db)
    kpis = await kpi_generator.get_all_kpis(user_id=current_user.id)

    # Get charts
    chart_generator = ChartDataGenerator(db)
    charts_data = [
        await chart_generator.get_pipeline_funnel(),
        await chart_generator.get_leads_by_status(),
        await chart_generator.get_leads_by_source(),
        await chart_generator.get_revenue_trend(),
        await chart_generator.get_activities_by_type(),
        await chart_generator.get_new_leads_trend(),
    ]

    # Convert to response format
    number_cards = [NumberCardData(**kpi) for kpi in kpis]
    charts = [
        ChartData(
            type=c["type"],
            title=c["title"],
            data=[ChartDataPoint(**d) for d in c["data"]],
        )
        for c in charts_data
    ]

    return DashboardResponse(
        number_cards=number_cards,
        charts=charts,
    )


@router.get("/kpis", response_model=List[NumberCardData])
async def get_kpis(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Get KPI number cards only."""
    generator = NumberCardGenerator(db)
    kpis = await generator.get_all_kpis(user_id=current_user.id)
    return [NumberCardData(**kpi) for kpi in kpis]


@router.get("/charts/pipeline-funnel", response_model=ChartData)
async def get_pipeline_funnel_chart(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Get pipeline funnel chart data."""
    generator = ChartDataGenerator(db)
    data = await generator.get_pipeline_funnel()
    return ChartData(
        type=data["type"],
        title=data["title"],
        data=[ChartDataPoint(**d) for d in data["data"]],
    )


@router.get("/charts/leads-by-status", response_model=ChartData)
async def get_leads_by_status_chart(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Get leads by status chart data."""
    generator = ChartDataGenerator(db)
    data = await generator.get_leads_by_status()
    return ChartData(
        type=data["type"],
        title=data["title"],
        data=[ChartDataPoint(**d) for d in data["data"]],
    )


@router.get("/charts/leads-by-source", response_model=ChartData)
async def get_leads_by_source_chart(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Get leads by source chart data."""
    generator = ChartDataGenerator(db)
    data = await generator.get_leads_by_source()
    return ChartData(
        type=data["type"],
        title=data["title"],
        data=[ChartDataPoint(**d) for d in data["data"]],
    )


@router.get("/charts/revenue-trend", response_model=ChartData)
async def get_revenue_trend_chart(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    months: int = 6,
):
    """Get monthly revenue trend chart data."""
    generator = ChartDataGenerator(db)
    data = await generator.get_revenue_trend(months=months)
    return ChartData(
        type=data["type"],
        title=data["title"],
        data=[ChartDataPoint(**d) for d in data["data"]],
    )


@router.get("/charts/activities", response_model=ChartData)
async def get_activities_chart(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    days: int = 30,
):
    """Get activities by type chart data."""
    generator = ChartDataGenerator(db)
    data = await generator.get_activities_by_type(days=days)
    return ChartData(
        type=data["type"],
        title=data["title"],
        data=[ChartDataPoint(**d) for d in data["data"]],
    )


@router.get("/charts/new-leads-trend", response_model=ChartData)
async def get_new_leads_trend_chart(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    weeks: int = 8,
):
    """Get new leads trend chart data."""
    generator = ChartDataGenerator(db)
    data = await generator.get_new_leads_trend(weeks=weeks)
    return ChartData(
        type=data["type"],
        title=data["title"],
        data=[ChartDataPoint(**d) for d in data["data"]],
    )


@router.get("/charts/conversion-rates", response_model=ChartData)
async def get_conversion_rates_chart(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Get conversion rates chart data."""
    generator = ChartDataGenerator(db)
    data = await generator.get_conversion_rates()
    return ChartData(
        type=data["type"],
        title=data["title"],
        data=[ChartDataPoint(**d) for d in data["data"]],
    )
