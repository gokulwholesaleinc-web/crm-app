"""Dashboard charts sub-router.

Each endpoint accepts an optional ``owner_id`` query param. Sales reps
are silently coerced to their own id by ``effective_owner_id``;
admin/manager may pass a peer's id or omit for the tenant-wide rollup
(``user_id=None`` flows through ``ChartDataGenerator`` as "no owner
filter"). Cache keys include viewer + target so admin sessions don't
share cached results.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from src.core.data_scope import DataScope, get_data_scope
from src.core.router_utils import CurrentUser, DBSession, effective_owner_id
from src.dashboard._utils import _get_cached, _parse_date, _set_cached
from src.dashboard.charts import ChartDataGenerator
from src.dashboard.schemas import ChartData, ChartDataPoint

charts_router = APIRouter(tags=["dashboard"])


@charts_router.get("/pipeline-funnel", response_model=ChartData)
async def get_pipeline_funnel_chart(
    current_user: CurrentUser,
    db: DBSession,
    response: Response,
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
    date_from: str | None = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: str | None = Query(None, description="End date (YYYY-MM-DD)"),
    owner_id: int | None = Query(None, description="Admin/manager: scope to a specific user"),
):
    """Get pipeline funnel chart data."""
    parsed_from = _parse_date(date_from)
    parsed_to = _parse_date(date_to)
    resolved_owner_id = effective_owner_id(data_scope, owner_id)
    cache_key = f"pipeline-funnel:{current_user.id}:{resolved_owner_id}:{date_from}:{date_to}"
    cached = _get_cached(cache_key)
    if cached is not None:
        response.headers["Cache-Control"] = "private, max-age=60"
        return cached

    generator = ChartDataGenerator(db, user_id=resolved_owner_id, date_from=parsed_from, date_to=parsed_to)
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
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
    date_from: str | None = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: str | None = Query(None, description="End date (YYYY-MM-DD)"),
    owner_id: int | None = Query(None, description="Admin/manager: scope to a specific user"),
):
    """Get leads by status chart data."""
    parsed_from = _parse_date(date_from)
    parsed_to = _parse_date(date_to)
    resolved_owner_id = effective_owner_id(data_scope, owner_id)
    cache_key = f"leads-by-status:{current_user.id}:{resolved_owner_id}:{date_from}:{date_to}"
    cached = _get_cached(cache_key)
    if cached is not None:
        response.headers["Cache-Control"] = "private, max-age=60"
        return cached

    generator = ChartDataGenerator(db, user_id=resolved_owner_id, date_from=parsed_from, date_to=parsed_to)
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
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
    date_from: str | None = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: str | None = Query(None, description="End date (YYYY-MM-DD)"),
    owner_id: int | None = Query(None, description="Admin/manager: scope to a specific user"),
):
    """Get leads by source chart data."""
    parsed_from = _parse_date(date_from)
    parsed_to = _parse_date(date_to)
    resolved_owner_id = effective_owner_id(data_scope, owner_id)
    cache_key = f"leads-by-source:{current_user.id}:{resolved_owner_id}:{date_from}:{date_to}"
    cached = _get_cached(cache_key)
    if cached is not None:
        response.headers["Cache-Control"] = "private, max-age=60"
        return cached

    generator = ChartDataGenerator(db, user_id=resolved_owner_id, date_from=parsed_from, date_to=parsed_to)
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
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
    months: int = 6,
    date_from: str | None = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: str | None = Query(None, description="End date (YYYY-MM-DD)"),
    owner_id: int | None = Query(None, description="Admin/manager: scope to a specific user"),
):
    """Get monthly revenue trend chart data."""
    parsed_from = _parse_date(date_from)
    parsed_to = _parse_date(date_to)
    resolved_owner_id = effective_owner_id(data_scope, owner_id)
    cache_key = f"revenue-trend:{current_user.id}:{resolved_owner_id}:{months}:{date_from}:{date_to}"
    cached = _get_cached(cache_key)
    if cached is not None:
        response.headers["Cache-Control"] = "private, max-age=60"
        return cached

    generator = ChartDataGenerator(db, user_id=resolved_owner_id, date_from=parsed_from, date_to=parsed_to)
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
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
    days: int = 30,
    date_from: str | None = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: str | None = Query(None, description="End date (YYYY-MM-DD)"),
    owner_id: int | None = Query(None, description="Admin/manager: scope to a specific user"),
):
    """Get activities by type chart data."""
    parsed_from = _parse_date(date_from)
    parsed_to = _parse_date(date_to)
    resolved_owner_id = effective_owner_id(data_scope, owner_id)
    cache_key = f"activities:{current_user.id}:{resolved_owner_id}:{days}:{date_from}:{date_to}"
    cached = _get_cached(cache_key)
    if cached is not None:
        response.headers["Cache-Control"] = "private, max-age=60"
        return cached

    generator = ChartDataGenerator(db, user_id=resolved_owner_id, date_from=parsed_from, date_to=parsed_to)
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
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
    weeks: int = 8,
    date_from: str | None = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: str | None = Query(None, description="End date (YYYY-MM-DD)"),
    owner_id: int | None = Query(None, description="Admin/manager: scope to a specific user"),
):
    """Get new leads trend chart data."""
    parsed_from = _parse_date(date_from)
    parsed_to = _parse_date(date_to)
    resolved_owner_id = effective_owner_id(data_scope, owner_id)
    cache_key = f"new-leads-trend:{current_user.id}:{resolved_owner_id}:{weeks}:{date_from}:{date_to}"
    cached = _get_cached(cache_key)
    if cached is not None:
        response.headers["Cache-Control"] = "private, max-age=60"
        return cached

    generator = ChartDataGenerator(db, user_id=resolved_owner_id, date_from=parsed_from, date_to=parsed_to)
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
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
    date_from: str | None = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: str | None = Query(None, description="End date (YYYY-MM-DD)"),
    owner_id: int | None = Query(None, description="Admin/manager: scope to a specific user"),
):
    """Get conversion rates chart data."""
    parsed_from = _parse_date(date_from)
    parsed_to = _parse_date(date_to)
    resolved_owner_id = effective_owner_id(data_scope, owner_id)
    cache_key = f"conversion-rates:{current_user.id}:{resolved_owner_id}:{date_from}:{date_to}"
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

    generator = ChartDataGenerator(db, user_id=resolved_owner_id, date_from=parsed_from, date_to=parsed_to)
    data = await generator.get_conversion_rates()
    result = ChartData(
        type=data["type"],
        title=data["title"],
        data=[ChartDataPoint(**d) for d in data["data"]],
    )
    _set_cached(cache_key, result)
    return result
