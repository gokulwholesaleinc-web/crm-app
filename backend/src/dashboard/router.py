"""Dashboard API routes."""

from typing import List
from fastapi import APIRouter
from fastapi.responses import Response
from src.core.router_utils import DBSession, CurrentUser
from src.dashboard.schemas import (
    NumberCardData,
    ChartData,
    ChartDataPoint,
    DashboardResponse,
    SalesFunnelResponse,
    FunnelStage,
    FunnelConversion,
)
from src.dashboard.number_cards import NumberCardGenerator
from src.dashboard.charts import ChartDataGenerator

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardResponse)
async def get_dashboard(
    current_user: CurrentUser,
    db: DBSession,
    response: Response,
):
    """Get full dashboard data including KPIs and charts."""
    # Get KPIs
    kpi_generator = NumberCardGenerator(db, user_id=current_user.id)
    kpis = await kpi_generator.get_all_kpis(user_id=current_user.id)

    # Get charts
    chart_generator = ChartDataGenerator(db, user_id=current_user.id)
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

    response.headers["Cache-Control"] = "private, max-age=60"
    return DashboardResponse(
        number_cards=number_cards,
        charts=charts,
    )


@router.get("/kpis", response_model=List[NumberCardData])
async def get_kpis(
    current_user: CurrentUser,
    db: DBSession,
):
    """Get KPI number cards only."""
    generator = NumberCardGenerator(db, user_id=current_user.id)
    kpis = await generator.get_all_kpis(user_id=current_user.id)
    return [NumberCardData(**kpi) for kpi in kpis]


@router.get("/charts/pipeline-funnel", response_model=ChartData)
async def get_pipeline_funnel_chart(
    current_user: CurrentUser,
    db: DBSession,
):
    """Get pipeline funnel chart data."""
    generator = ChartDataGenerator(db, user_id=current_user.id)
    data = await generator.get_pipeline_funnel()
    return ChartData(
        type=data["type"],
        title=data["title"],
        data=[ChartDataPoint(**d) for d in data["data"]],
    )


@router.get("/charts/leads-by-status", response_model=ChartData)
async def get_leads_by_status_chart(
    current_user: CurrentUser,
    db: DBSession,
):
    """Get leads by status chart data."""
    generator = ChartDataGenerator(db, user_id=current_user.id)
    data = await generator.get_leads_by_status()
    return ChartData(
        type=data["type"],
        title=data["title"],
        data=[ChartDataPoint(**d) for d in data["data"]],
    )


@router.get("/charts/leads-by-source", response_model=ChartData)
async def get_leads_by_source_chart(
    current_user: CurrentUser,
    db: DBSession,
):
    """Get leads by source chart data."""
    generator = ChartDataGenerator(db, user_id=current_user.id)
    data = await generator.get_leads_by_source()
    return ChartData(
        type=data["type"],
        title=data["title"],
        data=[ChartDataPoint(**d) for d in data["data"]],
    )


@router.get("/charts/revenue-trend", response_model=ChartData)
async def get_revenue_trend_chart(
    current_user: CurrentUser,
    db: DBSession,
    months: int = 6,
):
    """Get monthly revenue trend chart data."""
    generator = ChartDataGenerator(db, user_id=current_user.id)
    data = await generator.get_revenue_trend(months=months)
    return ChartData(
        type=data["type"],
        title=data["title"],
        data=[ChartDataPoint(**d) for d in data["data"]],
    )


@router.get("/charts/activities", response_model=ChartData)
async def get_activities_chart(
    current_user: CurrentUser,
    db: DBSession,
    days: int = 30,
):
    """Get activities by type chart data."""
    generator = ChartDataGenerator(db, user_id=current_user.id)
    data = await generator.get_activities_by_type(days=days)
    return ChartData(
        type=data["type"],
        title=data["title"],
        data=[ChartDataPoint(**d) for d in data["data"]],
    )


@router.get("/charts/new-leads-trend", response_model=ChartData)
async def get_new_leads_trend_chart(
    current_user: CurrentUser,
    db: DBSession,
    weeks: int = 8,
):
    """Get new leads trend chart data."""
    generator = ChartDataGenerator(db, user_id=current_user.id)
    data = await generator.get_new_leads_trend(weeks=weeks)
    return ChartData(
        type=data["type"],
        title=data["title"],
        data=[ChartDataPoint(**d) for d in data["data"]],
    )


@router.get("/funnel", response_model=SalesFunnelResponse)
async def get_sales_funnel(
    current_user: CurrentUser,
    db: DBSession,
):
    """Get sales funnel data with lead counts, conversion rates, and avg time in stage."""
    generator = ChartDataGenerator(db, user_id=current_user.id)
    data = await generator.get_sales_funnel()
    return SalesFunnelResponse(
        stages=[FunnelStage(**s) for s in data["stages"]],
        conversions=[FunnelConversion(**c) for c in data["conversions"]],
        avg_days_in_stage=data["avg_days_in_stage"],
    )


@router.get("/charts/conversion-rates", response_model=ChartData)
async def get_conversion_rates_chart(
    current_user: CurrentUser,
    db: DBSession,
):
    """Get conversion rates chart data."""
    generator = ChartDataGenerator(db, user_id=current_user.id)
    data = await generator.get_conversion_rates()
    return ChartData(
        type=data["type"],
        title=data["title"],
        data=[ChartDataPoint(**d) for d in data["data"]],
    )


# =========================================================================
# Sales Pipeline KPIs
# =========================================================================

from typing import Optional
from pydantic import BaseModel
from fastapi import Query
from sqlalchemy import select, func
from src.quotes.models import Quote
from src.proposals.models import Proposal
from src.payments.models import Payment
from src.core.currencies import (
    get_supported_currencies_list,
    get_base_currency,
    convert_amount,
)
from src.opportunities.models import Opportunity, PipelineStage


class SalesKPIResponse(BaseModel):
    quotes_sent: int
    proposals_sent: int
    payments_collected_total: float
    payments_collected_count: int
    quote_to_payment_conversion_rate: float


@router.get("/sales-kpis", response_model=SalesKPIResponse)
async def get_sales_kpis(
    current_user: CurrentUser,
    db: DBSession,
):
    """Get sales pipeline KPIs: quotes sent, proposals sent, payments collected, conversion rate."""
    # Quotes sent (status != draft)
    quotes_sent_result = await db.execute(
        select(func.count(Quote.id)).where(
            Quote.owner_id == current_user.id,
            Quote.status != "draft",
        )
    )
    quotes_sent = quotes_sent_result.scalar() or 0

    # Proposals sent (status != draft)
    proposals_sent_result = await db.execute(
        select(func.count(Proposal.id)).where(
            Proposal.created_by_id == current_user.id,
            Proposal.status != "draft",
        )
    )
    proposals_sent = proposals_sent_result.scalar() or 0

    # Payments collected (succeeded)
    payments_result = await db.execute(
        select(
            func.count(Payment.id),
            func.coalesce(func.sum(Payment.amount), 0),
        ).where(
            Payment.status == "succeeded",
        )
    )
    row = payments_result.one()
    payments_collected_count = row[0] or 0
    payments_collected_total = float(row[1] or 0)

    # Quote-to-payment conversion rate
    total_quotes_result = await db.execute(
        select(func.count(Quote.id)).where(
            Quote.owner_id == current_user.id,
        )
    )
    total_quotes = total_quotes_result.scalar() or 0

    # Quotes that led to a payment (accepted quotes)
    accepted_quotes_result = await db.execute(
        select(func.count(Quote.id)).where(
            Quote.owner_id == current_user.id,
            Quote.status == "accepted",
        )
    )
    accepted_quotes = accepted_quotes_result.scalar() or 0

    conversion_rate = round((accepted_quotes / total_quotes) * 100, 1) if total_quotes > 0 else 0.0

    return SalesKPIResponse(
        quotes_sent=quotes_sent,
        proposals_sent=proposals_sent,
        payments_collected_total=payments_collected_total,
        payments_collected_count=payments_collected_count,
        quote_to_payment_conversion_rate=conversion_rate,
    )


# =========================================================================
# Multi-Currency endpoints
# =========================================================================


@router.get("/currencies")
async def list_currencies(
    current_user: CurrentUser,
):
    """List all supported currencies with exchange rates."""
    return {
        "base_currency": get_base_currency(),
        "currencies": get_supported_currencies_list(),
    }


@router.get("/revenue/converted")
async def get_converted_revenue(
    current_user: CurrentUser,
    db: DBSession,
    target_currency: str = Query("USD", description="Target currency for conversion"),
):
    """Get pipeline revenue converted to a target currency."""
    # Fetch opportunities owned by current user with their pipeline stages
    result = await db.execute(
        select(Opportunity)
        .join(PipelineStage)
        .where(Opportunity.owner_id == current_user.id)
    )
    opportunities = result.scalars().all()

    total_pipeline_value = 0.0
    total_revenue = 0.0
    weighted_pipeline_value = 0.0
    open_deal_count = 0
    won_deal_count = 0

    for opp in opportunities:
        if opp.amount is None:
            continue

        converted = convert_amount(opp.amount, opp.currency or "USD", target_currency)
        stage = opp.pipeline_stage

        if stage.is_won:
            total_revenue += converted
            won_deal_count += 1
        elif not stage.is_lost:
            total_pipeline_value += converted
            open_deal_count += 1
            prob = opp.probability if opp.probability is not None else stage.probability
            weighted_pipeline_value += converted * (prob / 100)

    return {
        "target_currency": target_currency,
        "total_pipeline_value": round(total_pipeline_value, 2),
        "total_revenue": round(total_revenue, 2),
        "weighted_pipeline_value": round(weighted_pipeline_value, 2),
        "open_deal_count": open_deal_count,
        "won_deal_count": won_deal_count,
    }
