"""Dashboard API routes."""

import time
from datetime import date
from typing import Any, List, Optional
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from typing import Annotated as _Annotated  # alias to avoid shadowing existing Annotated-free code
from fastapi import Depends
from src.core.router_utils import DBSession, CurrentUser, effective_owner_id
from src.core.data_scope import DataScope, get_data_scope
from src.dashboard.schemas import (
    NumberCardData,
    ChartData,
    ChartDataPoint,
    DashboardResponse,
    SalesFunnelResponse,
    FunnelStage,
    FunnelConversion,
    ReportWidgetCreate,
    ReportWidgetUpdate,
    ReportWidgetResponse,
)
from src.dashboard.number_cards import NumberCardGenerator
from src.dashboard.charts import ChartDataGenerator


def _parse_date(date_str: Optional[str]) -> Optional[date]:
    """Parse a YYYY-MM-DD string to a date object."""
    if not date_str:
        return None
    return date.fromisoformat(date_str)

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

# Result-level cache for expensive dashboard queries (keyed by user_id).
# TTL is deliberately modest — dashboards are read-heavy and the data-scope /
# sharing layer does not currently invalidate this cache when role or share
# grants change, so stale data is bounded by the TTL below.
_dashboard_cache: dict[str, tuple[float, Any]] = {}
_DASHBOARD_CACHE_TTL = 180  # 3 minutes — long enough to let Neon auto-suspend


def _get_cached(key: str) -> Any | None:
    cached = _dashboard_cache.get(key)
    if cached and (time.monotonic() - cached[0]) < _DASHBOARD_CACHE_TTL:
        return cached[1]
    return None


def _set_cached(key: str, value: Any) -> None:
    _dashboard_cache[key] = (time.monotonic(), value)


@router.get("", response_model=DashboardResponse)
async def get_dashboard(
    current_user: CurrentUser,
    db: DBSession,
    response: Response,
    date_from: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
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


@router.get("/kpis", response_model=List[NumberCardData])
async def get_kpis(
    current_user: CurrentUser,
    db: DBSession,
    response: Response,
    date_from: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
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


@router.get("/charts/pipeline-funnel", response_model=ChartData)
async def get_pipeline_funnel_chart(
    current_user: CurrentUser,
    db: DBSession,
    response: Response,
    date_from: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
):
    """Get pipeline funnel chart data."""
    parsed_from = _parse_date(date_from)
    parsed_to = _parse_date(date_to)
    cache_key = f"pipeline-funnel:{current_user.id}:{date_from}:{date_to}"
    cached = _get_cached(cache_key)
    if cached is not None:
        response.headers["Cache-Control"] = "private, max-age=60"
        return cached

    generator = ChartDataGenerator(db, user_id=current_user.id, date_from=parsed_from, date_to=parsed_to)
    data = await generator.get_pipeline_funnel()
    result = ChartData(
        type=data["type"],
        title=data["title"],
        data=[ChartDataPoint(**d) for d in data["data"]],
    )
    _set_cached(cache_key, result)
    response.headers["Cache-Control"] = "private, max-age=60"
    return result


@router.get("/charts/leads-by-status", response_model=ChartData)
async def get_leads_by_status_chart(
    current_user: CurrentUser,
    db: DBSession,
    response: Response,
    date_from: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
):
    """Get leads by status chart data."""
    parsed_from = _parse_date(date_from)
    parsed_to = _parse_date(date_to)
    cache_key = f"leads-by-status:{current_user.id}:{date_from}:{date_to}"
    cached = _get_cached(cache_key)
    if cached is not None:
        response.headers["Cache-Control"] = "private, max-age=60"
        return cached

    generator = ChartDataGenerator(db, user_id=current_user.id, date_from=parsed_from, date_to=parsed_to)
    data = await generator.get_leads_by_status()
    result = ChartData(
        type=data["type"],
        title=data["title"],
        data=[ChartDataPoint(**d) for d in data["data"]],
    )
    _set_cached(cache_key, result)
    response.headers["Cache-Control"] = "private, max-age=60"
    return result


@router.get("/charts/leads-by-source", response_model=ChartData)
async def get_leads_by_source_chart(
    current_user: CurrentUser,
    db: DBSession,
    response: Response,
    date_from: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
):
    """Get leads by source chart data."""
    parsed_from = _parse_date(date_from)
    parsed_to = _parse_date(date_to)
    cache_key = f"leads-by-source:{current_user.id}:{date_from}:{date_to}"
    cached = _get_cached(cache_key)
    if cached is not None:
        response.headers["Cache-Control"] = "private, max-age=60"
        return cached

    generator = ChartDataGenerator(db, user_id=current_user.id, date_from=parsed_from, date_to=parsed_to)
    data = await generator.get_leads_by_source()
    result = ChartData(
        type=data["type"],
        title=data["title"],
        data=[ChartDataPoint(**d) for d in data["data"]],
    )
    _set_cached(cache_key, result)
    response.headers["Cache-Control"] = "private, max-age=60"
    return result


@router.get("/charts/revenue-trend", response_model=ChartData)
async def get_revenue_trend_chart(
    current_user: CurrentUser,
    db: DBSession,
    response: Response,
    months: int = 6,
    date_from: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
):
    """Get monthly revenue trend chart data."""
    parsed_from = _parse_date(date_from)
    parsed_to = _parse_date(date_to)
    cache_key = f"revenue-trend:{current_user.id}:{months}:{date_from}:{date_to}"
    cached = _get_cached(cache_key)
    if cached is not None:
        response.headers["Cache-Control"] = "private, max-age=60"
        return cached

    generator = ChartDataGenerator(db, user_id=current_user.id, date_from=parsed_from, date_to=parsed_to)
    data = await generator.get_revenue_trend(months=months)
    result = ChartData(
        type=data["type"],
        title=data["title"],
        data=[ChartDataPoint(**d) for d in data["data"]],
    )
    _set_cached(cache_key, result)
    response.headers["Cache-Control"] = "private, max-age=60"
    return result


@router.get("/charts/activities", response_model=ChartData)
async def get_activities_chart(
    current_user: CurrentUser,
    db: DBSession,
    response: Response,
    days: int = 30,
    date_from: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
):
    """Get activities by type chart data."""
    parsed_from = _parse_date(date_from)
    parsed_to = _parse_date(date_to)
    cache_key = f"activities:{current_user.id}:{days}:{date_from}:{date_to}"
    cached = _get_cached(cache_key)
    if cached is not None:
        response.headers["Cache-Control"] = "private, max-age=60"
        return cached

    generator = ChartDataGenerator(db, user_id=current_user.id, date_from=parsed_from, date_to=parsed_to)
    data = await generator.get_activities_by_type(days=days)
    result = ChartData(
        type=data["type"],
        title=data["title"],
        data=[ChartDataPoint(**d) for d in data["data"]],
    )
    _set_cached(cache_key, result)
    response.headers["Cache-Control"] = "private, max-age=60"
    return result


@router.get("/charts/new-leads-trend", response_model=ChartData)
async def get_new_leads_trend_chart(
    current_user: CurrentUser,
    db: DBSession,
    response: Response,
    weeks: int = 8,
    date_from: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
):
    """Get new leads trend chart data."""
    parsed_from = _parse_date(date_from)
    parsed_to = _parse_date(date_to)
    cache_key = f"new-leads-trend:{current_user.id}:{weeks}:{date_from}:{date_to}"
    cached = _get_cached(cache_key)
    if cached is not None:
        response.headers["Cache-Control"] = "private, max-age=60"
        return cached

    generator = ChartDataGenerator(db, user_id=current_user.id, date_from=parsed_from, date_to=parsed_to)
    data = await generator.get_new_leads_trend(weeks=weeks)
    result = ChartData(
        type=data["type"],
        title=data["title"],
        data=[ChartDataPoint(**d) for d in data["data"]],
    )
    _set_cached(cache_key, result)
    response.headers["Cache-Control"] = "private, max-age=60"
    return result


@router.get("/funnel", response_model=SalesFunnelResponse)
async def get_sales_funnel(
    current_user: CurrentUser,
    db: DBSession,
    date_from: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
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


@router.get("/charts/conversion-rates", response_model=ChartData)
async def get_conversion_rates_chart(
    current_user: CurrentUser,
    db: DBSession,
    date_from: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
):
    """Get conversion rates chart data."""
    parsed_from = _parse_date(date_from)
    parsed_to = _parse_date(date_to)
    cache_key = f"conversion-rates:{current_user.id}:{date_from}:{date_to}"
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

    generator = ChartDataGenerator(db, user_id=current_user.id, date_from=parsed_from, date_to=parsed_to)
    data = await generator.get_conversion_rates()
    result = ChartData(
        type=data["type"],
        title=data["title"],
        data=[ChartDataPoint(**d) for d in data["data"]],
    )
    _set_cached(cache_key, result)
    return result


# Sales Pipeline KPIs

from pydantic import BaseModel
from sqlalchemy import select, func, or_
from src.quotes.models import Quote
from src.proposals.models import Proposal
from src.payments.models import Payment
from src.core.currencies import (
    get_supported_currencies_list,
    get_base_currency,
    convert_amount,
)
from src.opportunities.models import Opportunity, PipelineStage
from src.leads.models import Lead


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
    date_from: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
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
    owner_id: Optional[int] = Query(None, description="Filter by owner ID"),
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


# Report Widgets

import json
from src.dashboard.models import DashboardReportWidget
from src.reports.models import SavedReport
from src.reports.service import ReportExecutor
from src.reports.schemas import ReportDefinition
from src.core.constants import HTTPStatus


@router.get("/widgets", response_model=List[ReportWidgetResponse])
async def list_report_widgets(
    current_user: CurrentUser,
    db: DBSession,
):
    """List the current user's dashboard report widgets."""
    result = await db.execute(
        select(DashboardReportWidget, SavedReport)
        .join(SavedReport, DashboardReportWidget.report_id == SavedReport.id)
        .where(DashboardReportWidget.user_id == current_user.id)
        .order_by(DashboardReportWidget.position)
    )
    rows = result.all()
    return [
        ReportWidgetResponse(
            id=widget.id,
            user_id=widget.user_id,
            report_id=widget.report_id,
            report_name=report.name,
            report_chart_type=report.chart_type,
            position=widget.position,
            width=widget.width,
            is_visible=widget.is_visible,
            created_at=widget.created_at,
        )
        for widget, report in rows
    ]


@router.post("/widgets", response_model=ReportWidgetResponse, status_code=HTTPStatus.CREATED)
async def create_report_widget(
    data: ReportWidgetCreate,
    current_user: CurrentUser,
    db: DBSession,
):
    """Pin a saved report to the dashboard as a widget."""
    # Verify report exists and user has access
    report_result = await db.execute(
        select(SavedReport).where(
            SavedReport.id == data.report_id,
            or_(
                SavedReport.created_by_id == current_user.id,
                SavedReport.is_public == True,
            ),
        )
    )
    report = report_result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Report not found")

    widget = DashboardReportWidget(
        user_id=current_user.id,
        report_id=data.report_id,
        position=data.position,
        width=data.width,
    )
    db.add(widget)
    await db.flush()
    await db.refresh(widget)

    return ReportWidgetResponse(
        id=widget.id,
        user_id=widget.user_id,
        report_id=widget.report_id,
        report_name=report.name,
        report_chart_type=report.chart_type,
        position=widget.position,
        width=widget.width,
        is_visible=widget.is_visible,
        created_at=widget.created_at,
    )


@router.patch("/widgets/{widget_id}", response_model=ReportWidgetResponse)
async def update_report_widget(
    widget_id: int,
    data: ReportWidgetUpdate,
    current_user: CurrentUser,
    db: DBSession,
):
    """Update a dashboard report widget's position, width, or visibility."""
    result = await db.execute(
        select(DashboardReportWidget).where(
            DashboardReportWidget.id == widget_id,
            DashboardReportWidget.user_id == current_user.id,
        )
    )
    widget = result.scalar_one_or_none()
    if not widget:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Widget not found")

    if data.position is not None:
        widget.position = data.position
    if data.width is not None:
        widget.width = data.width
    if data.is_visible is not None:
        widget.is_visible = data.is_visible

    await db.flush()
    await db.refresh(widget)

    # Fetch report for response
    report_result = await db.execute(
        select(SavedReport).where(SavedReport.id == widget.report_id)
    )
    report = report_result.scalar_one()

    return ReportWidgetResponse(
        id=widget.id,
        user_id=widget.user_id,
        report_id=widget.report_id,
        report_name=report.name,
        report_chart_type=report.chart_type,
        position=widget.position,
        width=widget.width,
        is_visible=widget.is_visible,
        created_at=widget.created_at,
    )


@router.delete("/widgets/{widget_id}", status_code=HTTPStatus.NO_CONTENT)
async def delete_report_widget(
    widget_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Remove a report widget from the dashboard."""
    result = await db.execute(
        select(DashboardReportWidget).where(
            DashboardReportWidget.id == widget_id,
            DashboardReportWidget.user_id == current_user.id,
        )
    )
    widget = result.scalar_one_or_none()
    if not widget:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Widget not found")

    await db.delete(widget)
    await db.flush()


@router.get("/widgets/{widget_id}/data")
async def get_report_widget_data(
    widget_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Execute the widget's underlying report and return chart data."""
    result = await db.execute(
        select(DashboardReportWidget, SavedReport)
        .join(SavedReport, DashboardReportWidget.report_id == SavedReport.id)
        .where(
            DashboardReportWidget.id == widget_id,
            DashboardReportWidget.user_id == current_user.id,
        )
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Widget not found")

    widget, report = row

    definition = ReportDefinition(
        entity_type=report.entity_type,
        metric=report.metric,
        metric_field=report.metric_field,
        group_by=report.group_by,
        date_group=report.date_group,
        filters=json.loads(report.filters) if report.filters else None,
        chart_type=report.chart_type,
    )

    executor = ReportExecutor(db, user_id=current_user.id)
    report_result = await executor.execute(definition)

    return {
        "widget_id": widget.id,
        "report_name": report.name,
        "chart_type": report.chart_type,
        "result": report_result,
    }
