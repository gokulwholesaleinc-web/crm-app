"""Pydantic response models for the marketing read API.

Shapes the per-endpoint payloads with the **data-trust contract** baked in (PART I
§5 / PART II §C): every response that fronts a tab carries a ``DataTrust`` block
(source, reporting timezone, last-synced timestamp, provisional flag, and any
withhold reason) so the UI can disclose freshness + attribution honestly instead
of the vendor's decorative "Live" dot.

KPI cards follow the locked anatomy — **label → value → delta → timeframe** (§C):
a ``MetricCard`` pairs a value with a ``MetricDelta`` (signed %, raw direction,
per-metric is-good polarity, and a zero-baseline "New" flag) so the frontend never
shows ``Infinity%``/``NaN%`` or relies on color alone.

E4: the blended overview is titled **"Spend vs platform-attributed conversion
value"** — never "Marketing P&L" (there is no revenue/COGS source).

Money/ratio fields are ``Decimal | None``: ``None`` means divide-by-zero / no prior
data (render "New"/em-dash). Pydantic v2 serializes ``Decimal`` losslessly.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


# ── data-trust + KPI primitives ──────────────────────────────────────────────
class DataTrust(BaseModel):
    """Per-response freshness/attribution disclosure (the trust contract)."""

    timezone: str  # the client's single reporting timezone (A8)
    last_synced_at: datetime | None = None  # actual last successful ingest, not page-load
    is_provisional: bool = False  # window includes still-settling recent days
    provisional_days: int = 0  # how many trailing days are provisional
    withheld_reason: str | None = None  # e.g. "multi_currency" — blended KPIs withheld (A9)
    sources: list[str] = []  # which platforms contributed (name the missing ones, don't zero)


class MetricDelta(BaseModel):
    """Period-over-period delta (A6): signed %, raw direction, polarity, New flag."""

    pct: float | None = None  # None → no prior data / withheld (never +100% from zero)
    direction: str = "flat"  # "up" | "down" | "flat" (raw movement)
    is_good: bool | None = None  # whether that movement is favorable for THIS metric
    is_new: bool = False  # True → render "New", not a fabricated percentage


class MetricCard(BaseModel):
    """KPI card: label → value → delta → timeframe (§C)."""

    key: str
    label: str
    value: Decimal | int | None = None  # None → em-dash (divide-by-zero / no data)
    format: str = "number"  # number | currency | percent | ratio
    delta: MetricDelta | None = None
    timeframe: str | None = None  # human label for the compared window


class Timeframe(BaseModel):
    """The window + the compare window the deltas were computed against."""

    date_from: date
    date_to: date
    compare_from: date | None = None
    compare_to: date | None = None
    entity_level: str = "account"


# ── /overview ────────────────────────────────────────────────────────────────
class OverviewResponse(BaseModel):
    """Blended cross-platform overview — "Spend vs platform-attributed conversion
    value" (E4 rename). ``cards`` is the KPI strip; ``withheld_reason`` non-null
    means blended KPIs were withheld for a multi-currency client (A9)."""

    title: str = "Spend vs platform-attributed conversion value"
    timeframe: Timeframe
    data_trust: DataTrust
    cards: list[MetricCard] = []
    spend: Decimal | None = None
    conversions: Decimal | None = None
    conversion_value: Decimal | None = None
    impressions: int | None = None
    clicks: int | None = None
    ctr: Decimal | None = None
    cpc: Decimal | None = None
    cost_per_conversion: Decimal | None = None
    roas: Decimal | None = None
    withheld_reason: str | None = None


# ── /series ──────────────────────────────────────────────────────────────────
class SeriesPoint(BaseModel):
    date: date
    spend: Decimal
    impressions: int
    clicks: int
    conversions: Decimal
    conversion_value: Decimal
    ctr: Decimal | None = None
    cpc: Decimal | None = None
    roas: Decimal | None = None
    is_provisional: bool = False  # greyed on the trend chart


class SeriesResponse(BaseModel):
    timeframe: Timeframe
    data_trust: DataTrust
    points: list[SeriesPoint] = []


# ── /allocation ──────────────────────────────────────────────────────────────
class AllocationSlice(BaseModel):
    platform: str
    currency: str | None = None  # this slice's account currency (A9 per-platform)
    spend: Decimal
    clicks: int
    impressions: int


class AllocationResponse(BaseModel):
    timeframe: Timeframe
    data_trust: DataTrust
    slices: list[AllocationSlice] = []
    total_spend: Decimal | None = None
    withheld_reason: str | None = None  # multi-currency → don't sum spend across currencies


# ── /day-of-week ─────────────────────────────────────────────────────────────
class DayOfWeekCard(BaseModel):
    day_of_week: int  # 0=Mon .. 6=Sun
    label: str
    spend: Decimal
    impressions: int
    clicks: int
    conversions: Decimal
    conversion_value: Decimal
    ctr: Decimal | None = None
    cpc: Decimal | None = None
    cost_per_conversion: Decimal | None = None
    roas: Decimal | None = None


class DayOfWeekResponse(BaseModel):
    timeframe: Timeframe
    data_trust: DataTrust
    days: list[DayOfWeekCard] = []


# ── /campaigns ───────────────────────────────────────────────────────────────
class CampaignRow(BaseModel):
    platform: str
    connection_id: int
    campaign_id: str | None = None
    name: str | None = None
    status: str | None = None
    spend: Decimal
    impressions: int
    clicks: int
    conversions: Decimal
    conversion_value: Decimal
    ctr: Decimal | None = None
    cpc: Decimal | None = None
    cost_per_conversion: Decimal | None = None
    conversion_rate: Decimal | None = None
    roas: Decimal | None = None


class CampaignsResponse(BaseModel):
    timeframe: Timeframe
    data_trust: DataTrust
    active_campaigns: int = 0
    campaigns: list[CampaignRow] = []


# ── /adgroups ────────────────────────────────────────────────────────────────
class AdGroupRow(BaseModel):
    platform: str
    connection_id: int
    adgroup_id: str | None = None
    campaign_id: str | None = None
    name: str | None = None
    status: str | None = None
    spend: Decimal
    impressions: int
    clicks: int
    conversions: Decimal
    conversion_value: Decimal
    ctr: Decimal | None = None
    cpc: Decimal | None = None
    cost_per_conversion: Decimal | None = None
    conversion_rate: Decimal | None = None
    roas: Decimal | None = None


class AdGroupsResponse(BaseModel):
    timeframe: Timeframe
    data_trust: DataTrust
    adgroups: list[AdGroupRow] = []


# ── /analytics (GA4 + GSC) ───────────────────────────────────────────────────
class Ga4Totals(BaseModel):
    sessions: int
    users: int
    new_users: int
    engaged_sessions: int
    # key_events IS GA4's conversion metric (H7) — no separate `conversions` field;
    # ad-platform conversions live on the Paid Media surfaces, not here.
    key_events: Decimal
    engagement_rate: Decimal | None = None
    is_sampled: bool = False  # A11: surface sampling, never hide it
    is_data_golden: bool = True  # H3: False ⇒ "(other)" overflow / not finalized → may not tie out


class Ga4SeriesPoint(BaseModel):
    date: date
    sessions: int
    users: int


class TrafficSource(BaseModel):
    channel: str
    sessions: int
    users: int


class TopPage(BaseModel):
    page: str
    sessions: int
    users: int


class GscTotals(BaseModel):
    clicks: int
    impressions: int
    ctr: Decimal | None = None
    position: Decimal | None = None


class GscQuery(BaseModel):
    query: str
    clicks: int
    impressions: int
    ctr: Decimal | None = None
    position: Decimal | None = None


class AnalyticsResponse(BaseModel):
    timeframe: Timeframe
    data_trust: DataTrust
    ga4_configured: bool = False  # False → "GA4 Property ID needed" empty state
    gsc_configured: bool = False
    ga4_totals: Ga4Totals | None = None
    ga4_series: list[Ga4SeriesPoint] = []
    traffic_sources: list[TrafficSource] = []
    top_pages: list[TopPage] = []
    gsc_totals: GscTotals | None = None
    gsc_queries: list[GscQuery] = []


# ── /site-health ─────────────────────────────────────────────────────────────
class SiteHealthSnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    url: str
    strategy: str
    captured_date: date
    performance_score: Decimal | None = None
    seo_score: Decimal | None = None
    accessibility_score: Decimal | None = None
    best_practices_score: Decimal | None = None
    lcp_ms: int | None = None
    cls: Decimal | None = None
    inp_ms: int | None = None


class SiteHealthResponse(BaseModel):
    timeframe: Timeframe
    data_trust: DataTrust
    latest: list[SiteHealthSnapshotOut] = []
    trend: list[SiteHealthSnapshotOut] = []


# ── /breakdown ───────────────────────────────────────────────────────────────
class BreakdownRow(BaseModel):
    date: date
    platform: str
    spend: Decimal
    impressions: int
    clicks: int
    conversions: Decimal
    conversion_value: Decimal
    ctr: Decimal | None = None
    cpc: Decimal | None = None
    cost_per_conversion: Decimal | None = None
    roas: Decimal | None = None


class BreakdownResponse(BaseModel):
    timeframe: Timeframe
    data_trust: DataTrust
    rows: list[BreakdownRow] = []


# ── /budget-pacing ───────────────────────────────────────────────────────────
class BudgetPaceRow(BaseModel):
    connection_id: int
    platform: str
    display_name: str | None = None
    budget: Decimal | None = None
    currency: str | None = None
    mtd_spend: Decimal
    projected_month_end: Decimal | None = None
    days_elapsed: int
    days_in_month: int
    pace_ratio: Decimal | None = None  # projected / budget (None when no budget)
    over_pace: bool | None = None


class BudgetPacingResponse(BaseModel):
    as_of: date
    data_trust: DataTrust
    rows: list[BudgetPaceRow] = []


# ── /sync-status ─────────────────────────────────────────────────────────────
class SyncRunSummary(BaseModel):
    run_type: str
    status: str
    rows_upserted: int
    started_at: datetime
    finished_at: datetime | None = None
    error_class: str | None = None
    window_start: date | None = None
    window_end: date | None = None


class ConnectionSyncStatus(BaseModel):
    connection_id: int
    platform: str
    display_name: str | None = None
    external_account_id: str
    status: str  # pending | active | needs_reauth | error | disabled
    last_synced_at: datetime | None = None
    last_error: str | None = None
    failure_count: int = 0
    reporting_timezone: str = "UTC"
    currency: str | None = None
    latest_run: SyncRunSummary | None = None


class SyncStatusResponse(BaseModel):
    connections: list[ConnectionSyncStatus] = []
