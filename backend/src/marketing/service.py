"""Read orchestration — windows + deltas + withhold + cache + data-trust.

Each public method is the seam a router endpoint calls: it (1) builds the compare
window when the caller didn't supply one (prior equal-length period, A6), (2) runs
the relevant ``reads`` aggregations, (3) computes per-metric deltas via ``deltas``
(settled-window + direction + zero-baseline), (4) applies the multi-currency
**withhold** (``aggregation.blended_withhold_reason`` gated on
``settings.MKTG_MULTI_CURRENCY``, A9) so a multi-currency client gets a *reason*
instead of a meaningless blended number, and (5) wraps the whole thing in the
explicit-keyed cache (D4) so the cache can never leak across companies.

Every response carries the data-trust block (A8/§C): one reporting timezone per
client (read from the client's connections, disclosed everywhere) and a real
``last_synced_at`` sourced from the connections' actual last successful ingest —
never page-load time.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings

from . import aggregation, cache, reads
from .deltas import compute_delta, default_compare_window, settled_window_end
from .models import PlatformConnection
from .schemas import (
    AdGroupRow,
    AdGroupsResponse,
    AllocationResponse,
    AllocationSlice,
    AnalyticsResponse,
    BreakdownResponse,
    BreakdownRow,
    BudgetPaceRow,
    BudgetPacingResponse,
    CampaignsResponse,
    ConnectionSyncStatus,
    DataTrust,
    DayOfWeekCard,
    DayOfWeekResponse,
    MetricCard,
    MetricDelta,
    OverviewResponse,
    SeriesPoint,
    SeriesResponse,
    SiteHealthResponse,
    SyncStatusResponse,
    Timeframe,
)

# Recent days whose ad/analytics numbers are still settling (greyed on trends,
# trimmed symmetrically from both delta compare windows, A6). Conservative single
# value v1; per-platform settling lives in the ingest settling-window (A7).
PROVISIONAL_DAYS = 2

# KPI cards surfaced on /overview. Additive cards are truly blendable across
# platforms (within one currency); conversion cards are withheld when >1 ad platform
# contributes because conversions are non-additive across platforms (BLEND).
_OVERVIEW_ADDITIVE_CARDS: tuple[tuple[str, str, str], ...] = (
    ("spend", "Total Spend", "currency"),
    ("cpc", "Blended CPC", "currency"),
)
_OVERVIEW_CONVERSION_CARDS: tuple[tuple[str, str, str], ...] = (
    ("conversions", "Total Conversions", "number"),
    ("cost_per_conversion", "Cost / Conversion", "currency"),
    ("roas", "ROAS", "ratio"),
)
# Conversion-derived fields withheld together when conversions can't be blended.
_CONVERSION_FIELDS = ("conversions", "conversion_value", "cost_per_conversion", "roas")


class MarketingReadService:
    """Orchestrates the read path for one DB session."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── client-level disclosure helpers (A8) ─────────────────────────────────
    async def _reporting_timezone(self, company_id: int) -> str:
        """The client's single reporting timezone (A8). All connections should
        agree; if they don't we take the most common and still disclose one."""
        rows = (
            await self.db.execute(
                select(
                    PlatformConnection.reporting_timezone,
                    func.count(PlatformConnection.id),
                )
                .where(PlatformConnection.company_id == company_id)
                .group_by(PlatformConnection.reporting_timezone)
                .order_by(func.count(PlatformConnection.id).desc())
            )
        ).all()
        for tz, _count in rows:
            if tz:
                return tz
        return "UTC"

    async def _last_synced_at(self, company_id: int) -> datetime | None:
        """The freshness of the STALEST contributing source — the truthful headline
        (§C), never page-load time. Deliberately ``MIN`` not ``MAX``: a single dead
        connection (ads stuck while GA4 keeps succeeding) must drag the chip to
        stale, not be masked by a healthy sibling.

        FRESHNESS-MIN: a connection that SHOULD have synced (enabled, not 'pending'
        first-sync, not 'disabled') but has NEVER synced (last_synced_at IS NULL)
        forces the chip to "never" — the prior ``isnot(None)`` filter excluded those,
        so a stuck-since-creation source could be masked by a healthy sibling. A
        brand-new 'pending' connection is excluded (no data yet is expected)."""
        never_synced = (
            await self.db.execute(
                select(func.count())
                .select_from(PlatformConnection)
                .where(
                    PlatformConnection.company_id == company_id,
                    PlatformConnection.is_enabled.is_(True),
                    PlatformConnection.status.notin_(("pending", "disabled")),
                    PlatformConnection.last_synced_at.is_(None),
                )
            )
        ).scalar_one()
        if never_synced:
            return None  # an active source has never produced data → "never"
        return (
            await self.db.execute(
                select(func.min(PlatformConnection.last_synced_at)).where(
                    PlatformConnection.company_id == company_id,
                    PlatformConnection.is_enabled.is_(True),
                    PlatformConnection.last_synced_at.isnot(None),
                )
            )
        ).scalar_one_or_none()

    async def _withhold_reason(self, company_id: int) -> str | None:
        """Multi-currency blended-KPI withhold (A9)."""
        currencies = await aggregation.distinct_currencies(self.db, company_id)
        return aggregation.blended_withhold_reason(
            currencies, multi_currency_enabled=settings.MKTG_MULTI_CURRENCY
        )

    async def _sources(self, company_id: int) -> list[str]:
        """Platforms with at least one connection (name them; don't zero-fill)."""
        rows = (
            await self.db.execute(
                select(PlatformConnection.platform)
                .where(PlatformConnection.company_id == company_id)
                .distinct()
            )
        ).all()
        return sorted({p for (p,) in rows if p})

    async def _data_trust(
        self, company_id: int, *, is_provisional: bool, withheld_reason: str | None
    ) -> DataTrust:
        return DataTrust(
            timezone=await self._reporting_timezone(company_id),
            last_synced_at=await self._last_synced_at(company_id),
            is_provisional=is_provisional,
            provisional_days=PROVISIONAL_DAYS if is_provisional else 0,
            withheld_reason=withheld_reason,
            sources=await self._sources(company_id),
        )

    @staticmethod
    def _resolve_compare(
        date_from: date,
        date_to: date,
        compare_from: date | None,
        compare_to: date | None,
    ) -> tuple[date, date]:
        """Use the caller's compare window or default to the prior equal period.

        COMPARE-ASYM: a one-sided window (only one of compare_from/compare_to) is a
        422, not a silent fall-through to the default — otherwise the response's
        Timeframe would disagree with what the caller asked for."""
        if (compare_from is None) != (compare_to is None):
            raise HTTPException(
                status_code=422,
                detail="compare_from and compare_to must be provided together",
            )
        if compare_from is not None and compare_to is not None:
            return compare_from, compare_to
        return default_compare_window(date_from, date_to)

    async def _conversions_cross_platform(
        self, company_id: int, date_from: date, date_to: date, entity_level: str
    ) -> bool:
        """True when >1 ad platform contributed in the window → the conversion-derived
        blended fields must be withheld (non-additive across platforms, BLEND)."""
        platforms = await aggregation.contributing_ad_platforms(
            self.db, company_id, date_from, date_to, entity_level=entity_level
        )
        return len(platforms) > 1

    # ── /overview ─────────────────────────────────────────────────────────────
    async def overview(
        self,
        company_id: int,
        date_from: date,
        date_to: date,
        *,
        compare_from: date | None = None,
        compare_to: date | None = None,
        entity_level: str = "account",
    ) -> OverviewResponse:
        cmp_from, cmp_to = self._resolve_compare(
            date_from, date_to, compare_from, compare_to
        )
        key = cache.make_key(
            company_id=company_id,
            endpoint="overview",
            date_from=date_from,
            date_to=date_to,
            compare_from=cmp_from,
            compare_to=cmp_to,
            entity_level=entity_level,
        )
        return await cache.get_or_compute(
            key,
            lambda: self._overview_uncached(
                company_id, date_from, date_to, cmp_from, cmp_to, entity_level
            ),
        )

    async def _overview_uncached(
        self,
        company_id: int,
        date_from: date,
        date_to: date,
        cmp_from: date,
        cmp_to: date,
        entity_level: str,
    ) -> OverviewResponse:
        withheld = await self._withhold_reason(company_id)
        timeframe = Timeframe(
            date_from=date_from,
            date_to=date_to,
            compare_from=cmp_from,
            compare_to=cmp_to,
            entity_level=entity_level,
        )
        data_trust = await self._data_trust(
            company_id, is_provisional=True, withheld_reason=withheld
        )

        # Multi-currency → withhold the blended numbers entirely (A9): return the
        # reason + empty cards, never a meaningless cross-currency sum.
        if withheld is not None:
            return OverviewResponse(
                timeframe=timeframe,
                data_trust=data_trust,
                cards=[],
                withheld_reason=withheld,
            )

        # Settled compare: trim provisional days symmetrically from both windows.
        cur_to = settled_window_end(date_to, provisional_days=PROVISIONAL_DAYS)
        prev_to = settled_window_end(cmp_to, provisional_days=PROVISIONAL_DAYS)

        current = await aggregation.ads_overview(
            self.db, company_id, date_from, cur_to, entity_level=entity_level
        )
        previous = await aggregation.ads_overview(
            self.db, company_id, cmp_from, prev_to, entity_level=entity_level
        )

        # BLEND: when >1 ad platform contributed, conversions/value/cost-per-conv/ROAS
        # are non-additive across platforms — withhold those (keep spend/clicks/impr).
        conv_withheld: str | None = None
        if await self._conversions_cross_platform(company_id, date_from, cur_to, entity_level):
            conv_withheld = "multi_platform_conversions"
            for bucket in (current, previous):
                for field in _CONVERSION_FIELDS:
                    bucket[field] = None
        elif await self._conversions_cross_platform(company_id, cmp_from, prev_to, entity_level):
            # Current window is single-platform (a valid number) but the COMPARE window
            # blended >1 platform — null only the previous conversion fields so the
            # delta renders "New"/em-dash instead of a fabricated % against a
            # non-additive baseline (don't compare a Google number to Google+Meta).
            for field in _CONVERSION_FIELDS:
                previous[field] = None

        card_specs = list(_OVERVIEW_ADDITIVE_CARDS)
        if conv_withheld is None:
            card_specs += list(_OVERVIEW_CONVERSION_CARDS)

        timeframe_label = f"vs {cmp_from.isoformat()} – {cmp_to.isoformat()}"
        cards = [
            self._card(key, label, fmt, current, previous, timeframe_label)
            for key, label, fmt in card_specs
        ]

        return OverviewResponse(
            timeframe=timeframe,
            data_trust=data_trust,
            cards=cards,
            spend=current["spend"],
            conversions=current["conversions"],
            conversion_value=current["conversion_value"],
            impressions=current["impressions"],
            clicks=current["clicks"],
            ctr=current["ctr"],
            cpc=current["cpc"],
            cost_per_conversion=current["cost_per_conversion"],
            roas=current["roas"],
            withheld_reason=None,
            conversions_withheld_reason=conv_withheld,
        )

    @staticmethod
    def _card(
        key: str,
        label: str,
        fmt: str,
        current: dict,
        previous: dict,
        timeframe_label: str,
    ) -> MetricCard:
        cur_val = current.get(key)
        prev_val = previous.get(key)
        d = compute_delta(key, cur_val, prev_val)
        return MetricCard(
            key=key,
            label=label,
            value=cur_val,
            format=fmt,
            delta=MetricDelta(
                pct=d.pct, direction=d.direction, is_good=d.is_good, is_new=d.is_new
            ),
            timeframe=timeframe_label,
        )

    # ── /series ───────────────────────────────────────────────────────────────
    async def series(
        self,
        company_id: int,
        date_from: date,
        date_to: date,
        *,
        entity_level: str = "account",
    ) -> SeriesResponse:
        key = cache.make_key(
            company_id=company_id,
            endpoint="series",
            date_from=date_from,
            date_to=date_to,
            entity_level=entity_level,
        )
        return await cache.get_or_compute(
            key,
            lambda: self._series_uncached(company_id, date_from, date_to, entity_level),
        )

    async def _series_uncached(
        self, company_id: int, date_from: date, date_to: date, entity_level: str
    ) -> SeriesResponse:
        timeframe = Timeframe(
            date_from=date_from, date_to=date_to, entity_level=entity_level
        )
        # H2: a multi-currency client's blended daily spend line is meaningless —
        # withhold (empty points + reason), matching /overview + /allocation.
        withheld = await self._withhold_reason(company_id)
        if withheld is not None:
            return SeriesResponse(
                timeframe=timeframe,
                data_trust=await self._data_trust(
                    company_id, is_provisional=True, withheld_reason=withheld
                ),
                points=[],
                withheld_reason=withheld,
            )

        raw = await reads.series(
            self.db, company_id, date_from, date_to, entity_level=entity_level
        )
        provisional_cutoff = settled_window_end(
            date_to, provisional_days=PROVISIONAL_DAYS
        )
        for point in raw:
            point["is_provisional"] = point["date"] > provisional_cutoff

        # BLEND: withhold per-day conversion-derived fields when >1 ad platform
        # contributes (spend/clicks/impressions stay — they're additive).
        conv_withheld: str | None = None
        if await self._conversions_cross_platform(company_id, date_from, date_to, entity_level):
            conv_withheld = "multi_platform_conversions"
            for point in raw:
                for field in ("conversions", "conversion_value", "roas"):
                    point[field] = None

        return SeriesResponse(
            timeframe=timeframe,
            data_trust=await self._data_trust(
                company_id, is_provisional=True, withheld_reason=None
            ),
            points=[SeriesPoint.model_validate(p) for p in raw],
            conversions_withheld_reason=conv_withheld,
        )

    # ── /allocation ───────────────────────────────────────────────────────────
    async def allocation(
        self,
        company_id: int,
        date_from: date,
        date_to: date,
        *,
        entity_level: str = "account",
    ) -> AllocationResponse:
        key = cache.make_key(
            company_id=company_id,
            endpoint="allocation",
            date_from=date_from,
            date_to=date_to,
            entity_level=entity_level,
        )
        return await cache.get_or_compute(
            key,
            lambda: self._allocation_uncached(
                company_id, date_from, date_to, entity_level
            ),
        )

    async def _allocation_uncached(
        self, company_id: int, date_from: date, date_to: date, entity_level: str
    ) -> AllocationResponse:
        withheld = await self._withhold_reason(company_id)
        slices = await reads.allocation(
            self.db, company_id, date_from, date_to, entity_level=entity_level
        )
        data_trust = await self._data_trust(
            company_id, is_provisional=True, withheld_reason=withheld
        )
        timeframe = Timeframe(
            date_from=date_from, date_to=date_to, entity_level=entity_level
        )
        # Per-platform spend is shown either way (each is in its own currency); a
        # blended TOTAL is withheld when currencies differ (don't sum across FX).
        total = (
            None
            if withheld is not None
            else sum((s["spend"] for s in slices), Decimal(0))
        )
        return AllocationResponse(
            timeframe=timeframe,
            data_trust=data_trust,
            slices=[AllocationSlice.model_validate(s) for s in slices],
            total_spend=total,
            withheld_reason=withheld,
        )

    # ── /day-of-week ──────────────────────────────────────────────────────────
    async def day_of_week(
        self,
        company_id: int,
        date_from: date,
        date_to: date,
        *,
        entity_level: str = "account",
    ) -> DayOfWeekResponse:
        key = cache.make_key(
            company_id=company_id,
            endpoint="day-of-week",
            date_from=date_from,
            date_to=date_to,
            entity_level=entity_level,
        )
        return await cache.get_or_compute(
            key,
            lambda: self._dow_uncached(company_id, date_from, date_to, entity_level),
        )

    async def _dow_uncached(
        self, company_id: int, date_from: date, date_to: date, entity_level: str
    ) -> DayOfWeekResponse:
        timeframe = Timeframe(
            date_from=date_from, date_to=date_to, entity_level=entity_level
        )
        # H2: withhold for multi-currency (blended spend across FX is meaningless).
        withheld = await self._withhold_reason(company_id)
        if withheld is not None:
            return DayOfWeekResponse(
                timeframe=timeframe,
                data_trust=await self._data_trust(
                    company_id, is_provisional=True, withheld_reason=withheld
                ),
                days=[],
                withheld_reason=withheld,
            )

        days = await reads.day_of_week(
            self.db, company_id, date_from, date_to, entity_level=entity_level
        )
        # BLEND: withhold conversion-derived per-DOW fields when >1 ad platform.
        conv_withheld: str | None = None
        if await self._conversions_cross_platform(company_id, date_from, date_to, entity_level):
            conv_withheld = "multi_platform_conversions"
            for day in days:
                for field in ("conversions", "conversion_value", "cost_per_conversion", "roas"):
                    day[field] = None

        return DayOfWeekResponse(
            timeframe=timeframe,
            data_trust=await self._data_trust(
                company_id, is_provisional=True, withheld_reason=None
            ),
            days=[DayOfWeekCard.model_validate(d) for d in days],
            conversions_withheld_reason=conv_withheld,
        )

    # ── /campaigns ────────────────────────────────────────────────────────────
    async def campaigns(
        self, company_id: int, date_from: date, date_to: date
    ) -> CampaignsResponse:
        key = cache.make_key(
            company_id=company_id,
            endpoint="campaigns",
            date_from=date_from,
            date_to=date_to,
            entity_level="campaign",
        )
        return await cache.get_or_compute(
            key, lambda: self._campaigns_uncached(company_id, date_from, date_to)
        )

    async def _campaigns_uncached(
        self, company_id: int, date_from: date, date_to: date
    ) -> CampaignsResponse:
        data = await reads.campaigns(self.db, company_id, date_from, date_to)
        return CampaignsResponse(
            timeframe=Timeframe(
                date_from=date_from, date_to=date_to, entity_level="campaign"
            ),
            data_trust=await self._data_trust(
                company_id, is_provisional=True, withheld_reason=None
            ),
            active_campaigns=data["active_campaigns"],
            campaigns=data["campaigns"],
        )

    # ── /adgroups ─────────────────────────────────────────────────────────────
    async def adgroups(
        self, company_id: int, date_from: date, date_to: date
    ) -> AdGroupsResponse:
        key = cache.make_key(
            company_id=company_id,
            endpoint="adgroups",
            date_from=date_from,
            date_to=date_to,
            entity_level="adgroup",
        )
        return await cache.get_or_compute(
            key, lambda: self._adgroups_uncached(company_id, date_from, date_to)
        )

    async def _adgroups_uncached(
        self, company_id: int, date_from: date, date_to: date
    ) -> AdGroupsResponse:
        rows = await reads.adgroups(self.db, company_id, date_from, date_to)
        return AdGroupsResponse(
            timeframe=Timeframe(
                date_from=date_from, date_to=date_to, entity_level="adgroup"
            ),
            data_trust=await self._data_trust(
                company_id, is_provisional=True, withheld_reason=None
            ),
            adgroups=[AdGroupRow.model_validate(r) for r in rows],
        )

    # ── /analytics ────────────────────────────────────────────────────────────
    async def analytics(
        self, company_id: int, date_from: date, date_to: date
    ) -> AnalyticsResponse:
        key = cache.make_key(
            company_id=company_id,
            endpoint="analytics",
            date_from=date_from,
            date_to=date_to,
        )
        return await cache.get_or_compute(
            key, lambda: self._analytics_uncached(company_id, date_from, date_to)
        )

    async def _analytics_uncached(
        self, company_id: int, date_from: date, date_to: date
    ) -> AnalyticsResponse:
        data = await reads.analytics(self.db, company_id, date_from, date_to)
        return AnalyticsResponse(
            timeframe=Timeframe(date_from=date_from, date_to=date_to),
            data_trust=await self._data_trust(
                company_id, is_provisional=True, withheld_reason=None
            ),
            ga4_configured=data["ga4_configured"],
            gsc_configured=data["gsc_configured"],
            ga4_totals=data["ga4_totals"] if data["ga4_configured"] else None,
            ga4_series=data["ga4_series"],
            traffic_sources=data["traffic_sources"],
            top_pages=data["top_pages"],
            gsc_totals=data["gsc_totals"] if data["gsc_configured"] else None,
            gsc_queries=data["gsc_queries"],
        )

    # ── /site-health ──────────────────────────────────────────────────────────
    async def site_health(
        self, company_id: int, date_from: date, date_to: date
    ) -> SiteHealthResponse:
        key = cache.make_key(
            company_id=company_id,
            endpoint="site-health",
            date_from=date_from,
            date_to=date_to,
        )
        return await cache.get_or_compute(
            key, lambda: self._site_health_uncached(company_id, date_from, date_to)
        )

    async def _site_health_uncached(
        self, company_id: int, date_from: date, date_to: date
    ) -> SiteHealthResponse:
        data = await reads.site_health(self.db, company_id, date_from, date_to)
        return SiteHealthResponse(
            timeframe=Timeframe(date_from=date_from, date_to=date_to),
            data_trust=await self._data_trust(
                company_id, is_provisional=False, withheld_reason=None
            ),
            latest=data["latest"],
            trend=data["trend"],
        )

    # ── /breakdown ────────────────────────────────────────────────────────────
    async def breakdown(
        self,
        company_id: int,
        date_from: date,
        date_to: date,
        *,
        entity_level: str = "account",
    ) -> BreakdownResponse:
        key = cache.make_key(
            company_id=company_id,
            endpoint="breakdown",
            date_from=date_from,
            date_to=date_to,
            entity_level=entity_level,
        )
        return await cache.get_or_compute(
            key,
            lambda: self._breakdown_uncached(
                company_id, date_from, date_to, entity_level
            ),
        )

    async def _breakdown_uncached(
        self, company_id: int, date_from: date, date_to: date, entity_level: str
    ) -> BreakdownResponse:
        rows = await reads.breakdown(
            self.db, company_id, date_from, date_to, entity_level=entity_level
        )
        return BreakdownResponse(
            timeframe=Timeframe(
                date_from=date_from, date_to=date_to, entity_level=entity_level
            ),
            data_trust=await self._data_trust(
                company_id, is_provisional=True, withheld_reason=None
            ),
            rows=[BreakdownRow.model_validate(r) for r in rows],
        )

    # ── /budget-pacing ────────────────────────────────────────────────────────
    async def budget_pacing(
        self, company_id: int, as_of: date
    ) -> BudgetPacingResponse:
        key = cache.make_key(
            company_id=company_id, endpoint="budget-pacing", date_to=as_of
        )
        return await cache.get_or_compute(
            key, lambda: self._budget_pacing_uncached(company_id, as_of)
        )

    async def _budget_pacing_uncached(
        self, company_id: int, as_of: date
    ) -> BudgetPacingResponse:
        rows = await reads.budget_pacing(self.db, company_id, as_of)
        return BudgetPacingResponse(
            as_of=as_of,
            data_trust=await self._data_trust(
                company_id, is_provisional=True, withheld_reason=None
            ),
            rows=[BudgetPaceRow.model_validate(r) for r in rows],
        )

    # ── /sync-status ──────────────────────────────────────────────────────────
    async def sync_status(self, company_id: int) -> SyncStatusResponse:
        # Not cached: freshness must always be live (it IS the freshness signal).
        connections = await reads.sync_status(self.db, company_id)
        return SyncStatusResponse(
            connections=[ConnectionSyncStatus.model_validate(c) for c in connections]
        )
