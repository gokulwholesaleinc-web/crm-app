"""Marketing Analytics read API — per-company, RBAC-gated, feature-flagged.

All endpoints are GET reads. Each one:
* enforces per-company RBAC isolation via ``_require_company_access`` — copied
  from ``meta/router.py:34`` — so a user scoped to company A can never read
  company B's marketing data;
* is dark unless ``settings.MKTG_ENABLED`` (the ``require_mktg_enabled``
  dependency returns 404 when the feature is off, so the surface is invisible
  before access lands);
* takes ``date_from``/``date_to`` (+ optional ``compare_from``/``compare_to`` and
  ``entity_level`` defaulting to ``account``) and delegates to
  ``MarketingReadService`` for windows + deltas + withhold + cache.

Write/refresh/connect endpoints are intentionally absent — the orchestrator wires
those to the ingest side. This router is read-only.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from src.companies.models import Company
from src.config import settings
from src.core.constants import ENTITY_TYPE_COMPANIES, HTTPStatus
from src.core.data_scope import DataScope, check_record_access_or_shared, get_data_scope
from src.core.router_utils import CurrentUser, DBSession
from src.marketing.schemas import (
    AdGroupsResponse,
    AllocationResponse,
    AnalyticsResponse,
    BreakdownResponse,
    BudgetPacingResponse,
    CampaignsResponse,
    DayOfWeekResponse,
    OverviewResponse,
    SeriesResponse,
    SiteHealthResponse,
    SyncStatusResponse,
)
from src.marketing.service import MarketingReadService

router = APIRouter(prefix="/api/marketing", tags=["marketing"])


def require_mktg_enabled() -> None:
    """Master feature flag — 404 (feature dark) when ``MKTG_ENABLED`` is False.

    404 rather than 403 so the endpoints are *invisible* (indistinguishable from a
    nonexistent route) until the feature is turned on per the phased rollout.
    """
    if not settings.MKTG_ENABLED:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Not Found")


# Applied to every route so the whole router goes dark behind one flag.
MktgEnabled = Annotated[None, Depends(require_mktg_enabled)]


async def _require_company_access(
    db, company_id: int, current_user, data_scope: DataScope
) -> Company:
    """Load the Company and enforce caller access (per-company RBAC isolation).

    Copied from ``meta/router.py`` — a 404 for a missing company, a 403 for a
    company the caller can't see, so company A's user can't read company B.
    """
    from sqlalchemy import select

    result = await db.execute(select(Company).where(Company.id == company_id))
    company = result.scalar_one_or_none()
    if company is None:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Company not found")
    check_record_access_or_shared(
        company,
        current_user,
        data_scope.role_name,
        shared_entity_ids=data_scope.get_shared_ids(ENTITY_TYPE_COMPANIES),
        entity_type=ENTITY_TYPE_COMPANIES,
    )
    return company


DateFrom = Annotated[date, Query(description="Window start (inclusive)")]
DateTo = Annotated[date, Query(description="Window end (inclusive)")]
CompareFrom = Annotated[date | None, Query(description="Compare window start")]
CompareTo = Annotated[date | None, Query(description="Compare window end")]
EntityLevel = Annotated[str, Query(description="account | campaign | adgroup")]
ScopeDep = Annotated[DataScope, Depends(get_data_scope)]


@router.get("/companies/{company_id}/overview", response_model=OverviewResponse)
async def get_overview(
    company_id: int,
    current_user: CurrentUser,
    db: DBSession,
    data_scope: ScopeDep,
    _: MktgEnabled,
    date_from: DateFrom,
    date_to: DateTo,
    compare_from: CompareFrom = None,
    compare_to: CompareTo = None,
    entity_level: EntityLevel = "account",
) -> OverviewResponse:
    """Blended overview KPI cards (E4: "Spend vs platform-attributed conversion value")."""
    await _require_company_access(db, company_id, current_user, data_scope)
    return await MarketingReadService(db).overview(
        company_id,
        date_from,
        date_to,
        compare_from=compare_from,
        compare_to=compare_to,
        entity_level=entity_level,
    )


@router.get("/companies/{company_id}/series", response_model=SeriesResponse)
async def get_series(
    company_id: int,
    current_user: CurrentUser,
    db: DBSession,
    data_scope: ScopeDep,
    _: MktgEnabled,
    date_from: DateFrom,
    date_to: DateTo,
    entity_level: EntityLevel = "account",
) -> SeriesResponse:
    """Daily spend/clicks/conversions trend (GROUP BY date)."""
    await _require_company_access(db, company_id, current_user, data_scope)
    return await MarketingReadService(db).series(
        company_id, date_from, date_to, entity_level=entity_level
    )


@router.get("/companies/{company_id}/allocation", response_model=AllocationResponse)
async def get_allocation(
    company_id: int,
    current_user: CurrentUser,
    db: DBSession,
    data_scope: ScopeDep,
    _: MktgEnabled,
    date_from: DateFrom,
    date_to: DateTo,
    entity_level: EntityLevel = "account",
) -> AllocationResponse:
    """Spend allocation by platform → donut."""
    await _require_company_access(db, company_id, current_user, data_scope)
    return await MarketingReadService(db).allocation(
        company_id, date_from, date_to, entity_level=entity_level
    )


@router.get("/companies/{company_id}/day-of-week", response_model=DayOfWeekResponse)
async def get_day_of_week(
    company_id: int,
    current_user: CurrentUser,
    db: DBSession,
    data_scope: ScopeDep,
    _: MktgEnabled,
    date_from: DateFrom,
    date_to: DateTo,
    entity_level: EntityLevel = "account",
) -> DayOfWeekResponse:
    """Day-of-week cards (ratio-of-sums per DOW)."""
    await _require_company_access(db, company_id, current_user, data_scope)
    return await MarketingReadService(db).day_of_week(
        company_id, date_from, date_to, entity_level=entity_level
    )


@router.get("/companies/{company_id}/campaigns", response_model=CampaignsResponse)
async def get_campaigns(
    company_id: int,
    current_user: CurrentUser,
    db: DBSession,
    data_scope: ScopeDep,
    _: MktgEnabled,
    date_from: DateFrom,
    date_to: DateTo,
) -> CampaignsResponse:
    """Per-campaign breakdown + Active Campaigns count (reads dim status)."""
    await _require_company_access(db, company_id, current_user, data_scope)
    return await MarketingReadService(db).campaigns(company_id, date_from, date_to)


@router.get("/companies/{company_id}/adgroups", response_model=AdGroupsResponse)
async def get_adgroups(
    company_id: int,
    current_user: CurrentUser,
    db: DBSession,
    data_scope: ScopeDep,
    _: MktgEnabled,
    date_from: DateFrom,
    date_to: DateTo,
) -> AdGroupsResponse:
    """Per-ad-group breakdown."""
    await _require_company_access(db, company_id, current_user, data_scope)
    return await MarketingReadService(db).adgroups(company_id, date_from, date_to)


@router.get("/companies/{company_id}/analytics", response_model=AnalyticsResponse)
async def get_analytics(
    company_id: int,
    current_user: CurrentUser,
    db: DBSession,
    data_scope: ScopeDep,
    _: MktgEnabled,
    date_from: DateFrom,
    date_to: DateTo,
) -> AnalyticsResponse:
    """GA4 + GSC website analytics (totals from dimension_type='total' only)."""
    await _require_company_access(db, company_id, current_user, data_scope)
    return await MarketingReadService(db).analytics(company_id, date_from, date_to)


@router.get("/companies/{company_id}/site-health", response_model=SiteHealthResponse)
async def get_site_health(
    company_id: int,
    current_user: CurrentUser,
    db: DBSession,
    data_scope: ScopeDep,
    _: MktgEnabled,
    date_from: DateFrom,
    date_to: DateTo,
) -> SiteHealthResponse:
    """Latest PageSpeed snapshots + score trend."""
    await _require_company_access(db, company_id, current_user, data_scope)
    return await MarketingReadService(db).site_health(company_id, date_from, date_to)


@router.get("/companies/{company_id}/breakdown", response_model=BreakdownResponse)
async def get_breakdown(
    company_id: int,
    current_user: CurrentUser,
    db: DBSession,
    data_scope: ScopeDep,
    _: MktgEnabled,
    date_from: DateFrom,
    date_to: DateTo,
    entity_level: EntityLevel = "account",
) -> BreakdownResponse:
    """Per-day per-platform daily breakdown table."""
    await _require_company_access(db, company_id, current_user, data_scope)
    return await MarketingReadService(db).breakdown(
        company_id, date_from, date_to, entity_level=entity_level
    )


@router.get("/companies/{company_id}/budget-pacing", response_model=BudgetPacingResponse)
async def get_budget_pacing(
    company_id: int,
    current_user: CurrentUser,
    db: DBSession,
    data_scope: ScopeDep,
    _: MktgEnabled,
    as_of: Annotated[date | None, Query(description="Pace as of this date (defaults today)")] = None,
) -> BudgetPacingResponse:
    """Budget vs MTD spend → projected month-end + over/under-pace."""
    await _require_company_access(db, company_id, current_user, data_scope)
    return await MarketingReadService(db).budget_pacing(
        company_id, as_of or date.today()
    )


@router.get("/companies/{company_id}/sync-status", response_model=SyncStatusResponse)
async def get_sync_status(
    company_id: int,
    current_user: CurrentUser,
    db: DBSession,
    data_scope: ScopeDep,
    _: MktgEnabled,
) -> SyncStatusResponse:
    """Per-connection freshness: last_synced_at / status / last_error + latest run."""
    await _require_company_access(db, company_id, current_user, data_scope)
    return await MarketingReadService(db).sync_status(company_id)
