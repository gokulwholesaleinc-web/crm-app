"""Dashboard API routes."""

from typing import Annotated as _Annotated  # alias to avoid shadowing existing Annotated-free code

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from src.core.data_scope import DataScope, get_data_scope
from src.core.router_utils import CurrentUser, DBSession, effective_owner_id
from src.dashboard._utils import (
    _DASHBOARD_CACHE_TTL,  # noqa: F401 — re-exported for tests/conftest.py
    _dashboard_cache,  # noqa: F401 — re-exported for tests/conftest.py
    _get_cached,
    _parse_date,
    _set_cached,
)
from src.dashboard.charts import ChartDataGenerator
from src.dashboard.charts_router import charts_router
from src.dashboard.number_cards import NumberCardGenerator
from src.dashboard.schemas import (
    ChartData,
    ChartDataPoint,
    DashboardResponse,
    FunnelConversion,
    FunnelStage,
    NumberCardData,
    SalesFunnelResponse,
)
from src.dashboard.widgets_router import widgets_router

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

# Mount sub-routers.
# charts_router handles all /api/dashboard/charts/* endpoints.
# widgets_router handles all /api/dashboard/widgets and /api/dashboard/widgets/* endpoints.
router.include_router(charts_router, prefix="/charts")
router.include_router(widgets_router, prefix="/widgets")


@router.get("", response_model=DashboardResponse)
async def get_dashboard(
    current_user: CurrentUser,
    db: DBSession,
    response: Response,
    date_from: str | None = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: str | None = Query(None, description="End date (YYYY-MM-DD)"),
):
    """Get full dashboard data including KPIs and charts."""
    parsed_from = _parse_date(date_from)
    parsed_to = _parse_date(date_to)
    cache_key = f"dashboard:{current_user.id}:{date_from}:{date_to}"
    cached = _get_cached(cache_key)
    if cached is not None:
        response.headers["Cache-Control"] = "private, max-age=60"
        return cached

    # Get KPIs
    kpi_generator = NumberCardGenerator(db, user_id=current_user.id, date_from=parsed_from, date_to=parsed_to)
    kpis = await kpi_generator.get_all_kpis(user_id=current_user.id)

    # Get charts
    chart_generator = ChartDataGenerator(db, user_id=current_user.id, date_from=parsed_from, date_to=parsed_to)
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

    result = DashboardResponse(
        number_cards=number_cards,
        charts=charts,
    )
    _set_cached(cache_key, result)
    response.headers["Cache-Control"] = "private, max-age=60"
    return result


@router.get("/kpis", response_model=list[NumberCardData])
async def get_kpis(
    current_user: CurrentUser,
    db: DBSession,
    response: Response,
    date_from: str | None = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: str | None = Query(None, description="End date (YYYY-MM-DD)"),
):
    """Get KPI number cards only."""
    parsed_from = _parse_date(date_from)
    parsed_to = _parse_date(date_to)
    cache_key = f"kpis:{current_user.id}:{date_from}:{date_to}"
    cached = _get_cached(cache_key)
    if cached is not None:
        response.headers["Cache-Control"] = "private, max-age=60"
        return cached

    generator = NumberCardGenerator(db, user_id=current_user.id, date_from=parsed_from, date_to=parsed_to)
    kpis = await generator.get_all_kpis(user_id=current_user.id)
    result = [NumberCardData(**kpi) for kpi in kpis]
    _set_cached(cache_key, result)
    response.headers["Cache-Control"] = "private, max-age=60"
    return result


@router.get("/funnel", response_model=SalesFunnelResponse)
async def get_sales_funnel(
    current_user: CurrentUser,
    db: DBSession,
    date_from: str | None = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: str | None = Query(None, description="End date (YYYY-MM-DD)"),
):
    """Get sales funnel data with lead counts, conversion rates, and avg time in stage."""
    parsed_from = _parse_date(date_from)
    parsed_to = _parse_date(date_to)
    cache_key = f"funnel:{current_user.id}:{date_from}:{date_to}"
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

    generator = ChartDataGenerator(db, user_id=current_user.id, date_from=parsed_from, date_to=parsed_to)
    data = await generator.get_sales_funnel()
    result = SalesFunnelResponse(
        stages=[FunnelStage(**s) for s in data["stages"]],
        conversions=[FunnelConversion(**c) for c in data["conversions"]],
        avg_days_in_stage=data["avg_days_in_stage"],
    )
    _set_cached(cache_key, result)
    return result


# Sales Pipeline KPIs

from pydantic import BaseModel
from sqlalchemy import func, select

from src.core.currencies import (
    convert_amount,
    get_base_currency,
    get_supported_currencies_list,
)
from src.leads.models import Lead
from src.opportunities.models import Opportunity, PipelineStage
from src.payments.models import Payment
from src.proposals.models import Proposal
from src.quotes.models import Quote


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
    response: Response,
    date_from: str | None = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: str | None = Query(None, description="End date (YYYY-MM-DD)"),
):
    """Get sales pipeline KPIs: quotes sent, proposals sent, payments collected, conversion rate."""
    parsed_from = _parse_date(date_from)
    parsed_to = _parse_date(date_to)
    cache_key = f"sales-kpis:{current_user.id}:{date_from}:{date_to}"
    cached = _get_cached(cache_key)
    if cached is not None:
        response.headers["Cache-Control"] = "private, max-age=60"
        return cached

    from datetime import datetime

    quotes_filters = [Quote.owner_id == current_user.id, Quote.status != "draft"]
    if parsed_from:
        quotes_filters.append(Quote.created_at >= datetime.combine(parsed_from, datetime.min.time()))
    if parsed_to:
        quotes_filters.append(Quote.created_at <= datetime.combine(parsed_to, datetime.max.time()))
    quotes_sent_result = await db.execute(
        select(func.count(Quote.id)).where(*quotes_filters)
    )

    proposals_filters = [Proposal.created_by_id == current_user.id, Proposal.status != "draft"]
    if parsed_from:
        proposals_filters.append(Proposal.created_at >= datetime.combine(parsed_from, datetime.min.time()))
    if parsed_to:
        proposals_filters.append(Proposal.created_at <= datetime.combine(parsed_to, datetime.max.time()))
    proposals_sent_result = await db.execute(
        select(func.count(Proposal.id)).where(*proposals_filters)
    )

    payments_filters = [Payment.status == "succeeded"]
    if parsed_from:
        payments_filters.append(Payment.created_at >= datetime.combine(parsed_from, datetime.min.time()))
    if parsed_to:
        payments_filters.append(Payment.created_at <= datetime.combine(parsed_to, datetime.max.time()))
    payments_result = await db.execute(
        select(
            func.count(Payment.id),
            func.coalesce(func.sum(Payment.amount), 0),
        ).where(*payments_filters)
    )

    total_quotes_filters = [Quote.owner_id == current_user.id]
    if parsed_from:
        total_quotes_filters.append(Quote.created_at >= datetime.combine(parsed_from, datetime.min.time()))
    if parsed_to:
        total_quotes_filters.append(Quote.created_at <= datetime.combine(parsed_to, datetime.max.time()))
    total_quotes_result = await db.execute(
        select(func.count(Quote.id)).where(*total_quotes_filters)
    )

    accepted_quotes_filters = [Quote.owner_id == current_user.id, Quote.status == "accepted"]
    if parsed_from:
        accepted_quotes_filters.append(Quote.created_at >= datetime.combine(parsed_from, datetime.min.time()))
    if parsed_to:
        accepted_quotes_filters.append(Quote.created_at <= datetime.combine(parsed_to, datetime.max.time()))
    accepted_quotes_result = await db.execute(
        select(func.count(Quote.id)).where(*accepted_quotes_filters)
    )

    quotes_sent = quotes_sent_result.scalar() or 0
    proposals_sent = proposals_sent_result.scalar() or 0

    row = payments_result.one()
    payments_collected_count = row[0] or 0
    payments_collected_total = float(row[1] or 0)

    total_quotes = total_quotes_result.scalar() or 0
    accepted_quotes = accepted_quotes_result.scalar() or 0

    conversion_rate = round((accepted_quotes / total_quotes) * 100, 1) if total_quotes > 0 else 0.0

    result = SalesKPIResponse(
        quotes_sent=quotes_sent,
        proposals_sent=proposals_sent,
        payments_collected_total=payments_collected_total,
        payments_collected_count=payments_collected_count,
        quote_to_payment_conversion_rate=conversion_rate,
    )
    _set_cached(cache_key, result)
    response.headers["Cache-Control"] = "private, max-age=60"
    return result


# Multi-Currency endpoints


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
    cache_key = f"revenue-converted:{current_user.id}:{target_currency}"
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

    # Fetch opportunities owned by current user with their pipeline stages
    result = await db.execute(
        select(Opportunity)
        .join(PipelineStage)
        .where(
            Opportunity.owner_id == current_user.id,
            Opportunity.amount.isnot(None),
        )
    )
    opportunities = result.scalars().all()

    total_pipeline_value = 0.0
    total_revenue = 0.0
    weighted_pipeline_value = 0.0
    open_deal_count = 0
    won_deal_count = 0

    for opp in opportunities:
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

    revenue_result = {
        "target_currency": target_currency,
        "total_pipeline_value": round(total_pipeline_value, 2),
        "total_revenue": round(total_revenue, 2),
        "weighted_pipeline_value": round(weighted_pipeline_value, 2),
        "open_deal_count": open_deal_count,
        "won_deal_count": won_deal_count,
    }
    _set_cached(cache_key, revenue_result)
    return revenue_result


# Unified Pipeline View


@router.get("/pipeline/unified")
async def get_unified_pipeline(
    current_user: CurrentUser,
    db: DBSession,
    data_scope: _Annotated[DataScope, Depends(get_data_scope)],
    owner_id: int | None = Query(None, description="Filter by owner ID"),
):
    """Get unified pipeline view with both lead and opportunity stages.

    Sales reps can only see their own pipeline; admin/manager may pass
    owner_id to view another user's. Spoofed owner_id is ignored.
    """
    resolved_owner_id = effective_owner_id(data_scope, owner_id)
    if resolved_owner_id is None and not data_scope.can_see_all():
        resolved_owner_id = current_user.id

    # Get lead pipeline stages
    lead_stages_result = await db.execute(
        select(PipelineStage)
        .where(PipelineStage.pipeline_type == "lead")
        .where(PipelineStage.is_active == True)
        .order_by(PipelineStage.order)
    )
    lead_stages = lead_stages_result.scalars().all()

    lead_stages_data = []
    for stage in lead_stages:
        leads_query = select(Lead).where(Lead.pipeline_stage_id == stage.id)
        if resolved_owner_id is not None:
            leads_query = leads_query.where(Lead.owner_id == resolved_owner_id)
        leads_query = leads_query.order_by(Lead.score.desc())

        leads_result = await db.execute(leads_query)
        leads = leads_result.scalars().all()

        lead_stages_data.append({
            "stage_id": stage.id,
            "stage_name": stage.name,
            "color": stage.color,
            "entity_type": "lead",
            "items": [
                {
                    "id": lead.id,
                    "name": lead.full_name,
                    "entity_type": "lead",
                    "value": lead.budget_amount,
                    "owner_id": lead.owner_id,
                    "company_name": lead.company_name,
                    "score": lead.score,
                }
                for lead in leads
            ],
            "count": len(leads),
        })

    # Get opportunity pipeline stages
    opp_stages_result = await db.execute(
        select(PipelineStage)
        .where(PipelineStage.pipeline_type == "opportunity")
        .where(PipelineStage.is_active == True)
        .order_by(PipelineStage.order)
    )
    opp_stages = opp_stages_result.scalars().all()

    opp_stages_data = []
    for stage in opp_stages:
        opps_query = select(Opportunity).where(Opportunity.pipeline_stage_id == stage.id)
        if resolved_owner_id is not None:
            opps_query = opps_query.where(Opportunity.owner_id == resolved_owner_id)
        opps_query = opps_query.order_by(Opportunity.expected_close_date.asc().nullslast())

        opps_result = await db.execute(opps_query)
        opps = opps_result.scalars().all()

        total_value = sum(opp.amount or 0 for opp in opps)

        opp_stages_data.append({
            "stage_id": stage.id,
            "stage_name": stage.name,
            "color": stage.color,
            "entity_type": "opportunity",
            "items": [
                {
                    "id": opp.id,
                    "name": opp.name,
                    "entity_type": "opportunity",
                    "value": opp.amount,
                    "owner_id": opp.owner_id,
                    "company_name": opp.company.name if opp.company else None,
                    "contact_name": opp.contact.full_name if opp.contact else None,
                }
                for opp in opps
            ],
            "count": len(opps),
            "total_value": total_value,
        })

    return {
        "lead_stages": lead_stages_data,
        "opportunity_stages": opp_stages_data,
    }
