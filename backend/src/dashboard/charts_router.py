"""Dashboard charts sub-router."""

from typing import Optional
from fastapi import APIRouter, Query
from fastapi.responses import Response
from src.core.router_utils import DBSession, CurrentUser
from src.dashboard.schemas import ChartData, ChartDataPoint
from src.dashboard.charts import ChartDataGenerator
from src.dashboard._utils import _parse_date, _get_cached, _set_cached

charts_router = APIRouter(tags=["dashboard"])


@charts_router.get("/pipeline-funnel", response_model=ChartData)
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


@charts_router.get("/leads-by-status", response_model=ChartData)
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


@charts_router.get("/leads-by-source", response_model=ChartData)
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


@charts_router.get("/revenue-trend", response_model=ChartData)
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


@charts_router.get("/activities", response_model=ChartData)
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


@charts_router.get("/new-leads-trend", response_model=ChartData)
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


@charts_router.get("/conversion-rates", response_model=ChartData)
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
