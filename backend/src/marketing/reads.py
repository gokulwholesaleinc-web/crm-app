"""Per-tab read aggregations — ratio-of-sums in SQL (A5), one entity_level (A2).

Layers the full per-tab endpoint surface (series, allocation, day-of-week,
campaigns, ad-groups, analytics, site-health, breakdown, budget-pacing,
sync-status) on top of the locked ``aggregation`` primitives and the ``money``
helpers. The contract these all honor:

* **Ratio-of-sums, never avg-of-daily-ratios** (A5): every CTR/CPC/ROAS is
  ``SUM(num)/SUM(den)`` via ``aggregation._ratio`` — including the Day-of-Week
  cards and every rollup. ÷0 → ``None`` so the UI shows "New"/an em-dash.
* **Exactly one ``entity_level`` per ads query** (A2) so mixed-grain rows can't
  double-count. Account totals read ``entity_level='account'``; campaign/ad-group
  tables read their own level joined to the dimension for name + current status.
* **Conversions are never summed across platforms** — non-additive (per platform
  only). ``allocation`` sums *spend* (additive within one currency) per platform.
* **GA4/GSC totals come ONLY from ``dimension_type='total'`` rows** (A11), never
  by summing dimension rows; traffic sources/pages/queries read their own
  ``dimension_type``.
* **No stored ratio is ever returned** — all ratios are computed live here.

These are pure read helpers (no cache, no RBAC, no window math); ``service``
orchestrates windows + deltas + cache + the multi-currency withhold on top.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Integer, Numeric, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .aggregation import _ratio
from .models import (
    AdsDailyMetric,
    AnalyticsDaily,
    BudgetPeriod,
    MarketingAdGroup,
    MarketingCampaign,
    MarketingSyncRun,
    PlatformConnection,
    SiteHealthSnapshot,
)
from .money import q6

# Statuses that count a campaign as "active" for the Campaigns-tab KPI (A3 — read
# the current dim status, not the historical facts).
_ACTIVE_CAMPAIGN_STATUSES = ("enabled", "active")


def _money(value) -> Decimal:
    return q6(value or 0)


def _int(value) -> int:
    return int(value or 0)


def _ads_metrics(
    spend,
    impressions,
    clicks,
    conversions,
    conversion_value,
    *,
    cost_per_conversion: bool = False,
    conversion_rate: bool = False,
) -> dict:
    """Coerce raw SUM() results to typed measures + ratio-of-sums KPIs (A5).

    One place to coerce so the per-row loops never reassign their loop variables.
    Core ctr/cpc/roas always; cost-per-conversion / conversion-rate are opt-in so
    each row dict matches its response schema exactly.
    """
    s = _money(spend)
    conv = _money(conversions)
    cv = _money(conversion_value)
    cl = _int(clicks)
    imp = _int(impressions)
    out = {
        "spend": s,
        "impressions": imp,
        "clicks": cl,
        "conversions": conv,
        "conversion_value": cv,
        "ctr": _ratio(cl, imp),
        "cpc": _ratio(s, cl),
        "roas": _ratio(cv, s),
    }
    if cost_per_conversion:
        out["cost_per_conversion"] = _ratio(s, conv)
    if conversion_rate:
        out["conversion_rate"] = _ratio(conv, cl)
    return out


# ════════════════════════════════════════════════════════════════════════════
# Daily trends (series) — GROUP BY date
# ════════════════════════════════════════════════════════════════════════════
async def series(
    session: AsyncSession,
    company_id: int,
    date_from: date,
    date_to: date,
    *,
    entity_level: str = "account",
) -> list[dict]:
    """Daily spend/clicks/impressions/conversions trend, one row per date.

    Per-day ratios are still ratio-of-sums *within that day* (A5). Days with no
    rows are simply absent (the caller decides how to grey/zero-fill); we never
    fabricate a row. Ordered ascending so charts render left-to-right.
    """
    rows = (
        await session.execute(
            select(
                AdsDailyMetric.date,
                func.coalesce(func.sum(AdsDailyMetric.spend), 0),
                func.coalesce(func.sum(AdsDailyMetric.impressions), 0),
                func.coalesce(func.sum(AdsDailyMetric.clicks), 0),
                func.coalesce(func.sum(AdsDailyMetric.conversions), 0),
                func.coalesce(func.sum(AdsDailyMetric.conversion_value), 0),
            )
            .where(
                AdsDailyMetric.company_id == company_id,
                AdsDailyMetric.entity_level == entity_level,
                AdsDailyMetric.date >= date_from,
                AdsDailyMetric.date <= date_to,
            )
            .group_by(AdsDailyMetric.date)
            .order_by(AdsDailyMetric.date)
        )
    ).all()

    out: list[dict] = []
    for d, spend, impressions, clicks, conversions, conversion_value in rows:
        out.append(
            {"date": d, **_ads_metrics(spend, impressions, clicks, conversions, conversion_value)}
        )
    return out


# ════════════════════════════════════════════════════════════════════════════
# Spend allocation by platform → donut
# ════════════════════════════════════════════════════════════════════════════
async def allocation(
    session: AsyncSession,
    company_id: int,
    date_from: date,
    date_to: date,
    *,
    entity_level: str = "account",
) -> list[dict]:
    """Spend per platform (Google vs Meta vs …) for the donut.

    Only *spend* is summed (additive within a currency); conversions are NOT
    aggregated here because they are non-additive across platforms. The withhold
    for multi-currency clients is applied one layer up in ``service``.
    """
    rows = (
        await session.execute(
            select(
                AdsDailyMetric.platform,
                AdsDailyMetric.currency,
                func.coalesce(func.sum(AdsDailyMetric.spend), 0),
                func.coalesce(func.sum(AdsDailyMetric.clicks), 0),
                func.coalesce(func.sum(AdsDailyMetric.impressions), 0),
            )
            .where(
                AdsDailyMetric.company_id == company_id,
                AdsDailyMetric.entity_level == entity_level,
                AdsDailyMetric.date >= date_from,
                AdsDailyMetric.date <= date_to,
            )
            # Group by currency too so a multi-currency client's per-platform spend
            # is shown each in its OWN currency (A9) rather than blended/mislabeled.
            .group_by(AdsDailyMetric.platform, AdsDailyMetric.currency)
            .order_by(func.coalesce(func.sum(AdsDailyMetric.spend), 0).desc())
        )
    ).all()

    return [
        {
            "platform": platform,
            "currency": currency,
            "spend": _money(spend),
            "clicks": _int(clicks),
            "impressions": _int(impressions),
        }
        for platform, currency, spend, clicks, impressions in rows
    ]


# ════════════════════════════════════════════════════════════════════════════
# Day-of-week cards — ratio-of-sums per DOW
# ════════════════════════════════════════════════════════════════════════════
# Mon..Sun labels keyed by Python's date.weekday() (Mon=0). Done in Python rather
# than SQL's EXTRACT('dow') so the same code is correct on both SQLite (test) and
# Postgres (prod) — the sums are taken per-date in SQL, the DOW bucketing in
# Python, so it is still ratio-of-sums (A5), not avg-of-daily-ratios.
_DOW_LABELS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


async def day_of_week(
    session: AsyncSession,
    company_id: int,
    date_from: date,
    date_to: date,
    *,
    entity_level: str = "account",
) -> list[dict]:
    """Spend/clicks/conversions + ratio-of-sums KPIs bucketed by day of week.

    Sums are accumulated per-DOW across the window then divided ONCE (A5) — e.g.
    CPC for "Monday" is ``SUM(spend on Mondays)/SUM(clicks on Mondays)``, never the
    mean of each Monday's CPC. Returns all 7 days in Mon..Sun order; days with no
    data carry zero sums and ``None`` ratios.
    """
    rows = (
        await session.execute(
            select(
                AdsDailyMetric.date,
                func.coalesce(func.sum(AdsDailyMetric.spend), 0),
                func.coalesce(func.sum(AdsDailyMetric.impressions), 0),
                func.coalesce(func.sum(AdsDailyMetric.clicks), 0),
                func.coalesce(func.sum(AdsDailyMetric.conversions), 0),
                func.coalesce(func.sum(AdsDailyMetric.conversion_value), 0),
            )
            .where(
                AdsDailyMetric.company_id == company_id,
                AdsDailyMetric.entity_level == entity_level,
                AdsDailyMetric.date >= date_from,
                AdsDailyMetric.date <= date_to,
            )
            .group_by(AdsDailyMetric.date)
        )
    ).all()

    # Accumulate sums per DOW first, divide once after.
    buckets: list[dict[str, Decimal | int]] = [
        {"spend": Decimal(0), "impressions": 0, "clicks": 0, "conversions": Decimal(0), "conversion_value": Decimal(0)}
        for _ in range(7)
    ]
    for d, spend, impressions, clicks, conversions, conversion_value in rows:
        b = buckets[d.weekday()]
        b["spend"] = Decimal(b["spend"]) + Decimal(spend or 0)
        b["impressions"] = int(b["impressions"]) + _int(impressions)
        b["clicks"] = int(b["clicks"]) + _int(clicks)
        b["conversions"] = Decimal(b["conversions"]) + Decimal(conversions or 0)
        b["conversion_value"] = Decimal(b["conversion_value"]) + Decimal(conversion_value or 0)

    out: list[dict] = []
    for idx, label in enumerate(_DOW_LABELS):
        b = buckets[idx]
        spend = q6(b["spend"])
        conversions = q6(b["conversions"])
        conversion_value = q6(b["conversion_value"])
        clicks = int(b["clicks"])
        impressions = int(b["impressions"])
        out.append(
            {
                "day_of_week": idx,
                "label": label,
                "spend": spend,
                "impressions": impressions,
                "clicks": clicks,
                "conversions": conversions,
                "conversion_value": conversion_value,
                "ctr": _ratio(clicks, impressions),
                "cpc": _ratio(spend, clicks),
                "cost_per_conversion": _ratio(spend, conversions),
                "roas": _ratio(conversion_value, spend),
            }
        )
    return out


# ════════════════════════════════════════════════════════════════════════════
# Campaigns — facts joined to the dim for name + current status
# ════════════════════════════════════════════════════════════════════════════
async def campaigns(
    session: AsyncSession,
    company_id: int,
    date_from: date,
    date_to: date,
) -> dict:
    """Per-campaign ratio-of-sums table + the "Active Campaigns" count.

    Facts are read at ``entity_level='campaign'`` and joined to
    ``marketing_campaigns`` for ``name``/``status`` (A3). "Active Campaigns" reads
    the current dim status (REMOVED campaigns still keep historical facts), so it
    is independent of whether they spent in the window.
    """
    # Per-campaign measures (one entity_level → no double counting, A2).
    fact_rows = (
        await session.execute(
            select(
                AdsDailyMetric.platform,
                AdsDailyMetric.connection_id,
                AdsDailyMetric.campaign_id,
                MarketingCampaign.name,
                MarketingCampaign.status,
                func.coalesce(func.sum(AdsDailyMetric.spend), 0),
                func.coalesce(func.sum(AdsDailyMetric.impressions), 0),
                func.coalesce(func.sum(AdsDailyMetric.clicks), 0),
                func.coalesce(func.sum(AdsDailyMetric.conversions), 0),
                func.coalesce(func.sum(AdsDailyMetric.conversion_value), 0),
            )
            .outerjoin(
                MarketingCampaign,
                (MarketingCampaign.connection_id == AdsDailyMetric.connection_id)
                & (MarketingCampaign.campaign_id == AdsDailyMetric.campaign_id),
            )
            .where(
                AdsDailyMetric.company_id == company_id,
                AdsDailyMetric.entity_level == "campaign",
                AdsDailyMetric.date >= date_from,
                AdsDailyMetric.date <= date_to,
            )
            .group_by(
                AdsDailyMetric.platform,
                AdsDailyMetric.connection_id,
                AdsDailyMetric.campaign_id,
                MarketingCampaign.name,
                MarketingCampaign.status,
            )
            .order_by(func.coalesce(func.sum(AdsDailyMetric.spend), 0).desc())
        )
    ).all()

    items: list[dict] = []
    for (
        platform,
        connection_id,
        campaign_id,
        name,
        status,
        spend,
        impressions,
        clicks,
        conversions,
        conversion_value,
    ) in fact_rows:
        items.append(
            {
                "platform": platform,
                "connection_id": connection_id,
                "campaign_id": campaign_id,
                "name": name,
                "status": status,
                **_ads_metrics(
                    spend, impressions, clicks, conversions, conversion_value,
                    cost_per_conversion=True,
                    conversion_rate=True,
                ),
            }
        )

    active_count = (
        await session.execute(
            select(func.count(MarketingCampaign.id))
            .join(
                PlatformConnection,
                PlatformConnection.id == MarketingCampaign.connection_id,
            )
            .where(
                PlatformConnection.company_id == company_id,
                func.lower(MarketingCampaign.status).in_(_ACTIVE_CAMPAIGN_STATUSES),
            )
        )
    ).scalar() or 0

    return {"active_campaigns": int(active_count), "campaigns": items}


# ════════════════════════════════════════════════════════════════════════════
# Ad groups — facts joined to the ad-group dim
# ════════════════════════════════════════════════════════════════════════════
async def adgroups(
    session: AsyncSession,
    company_id: int,
    date_from: date,
    date_to: date,
) -> list[dict]:
    """Per-ad-group ratio-of-sums table (``entity_level='adgroup'``, A2)."""
    rows = (
        await session.execute(
            select(
                AdsDailyMetric.platform,
                AdsDailyMetric.connection_id,
                AdsDailyMetric.adgroup_id,
                AdsDailyMetric.campaign_id,
                MarketingAdGroup.name,
                MarketingAdGroup.status,
                func.coalesce(func.sum(AdsDailyMetric.spend), 0),
                func.coalesce(func.sum(AdsDailyMetric.impressions), 0),
                func.coalesce(func.sum(AdsDailyMetric.clicks), 0),
                func.coalesce(func.sum(AdsDailyMetric.conversions), 0),
                func.coalesce(func.sum(AdsDailyMetric.conversion_value), 0),
            )
            .outerjoin(
                MarketingAdGroup,
                (MarketingAdGroup.connection_id == AdsDailyMetric.connection_id)
                & (MarketingAdGroup.adgroup_id == AdsDailyMetric.adgroup_id),
            )
            .where(
                AdsDailyMetric.company_id == company_id,
                AdsDailyMetric.entity_level == "adgroup",
                AdsDailyMetric.date >= date_from,
                AdsDailyMetric.date <= date_to,
            )
            .group_by(
                AdsDailyMetric.platform,
                AdsDailyMetric.connection_id,
                AdsDailyMetric.adgroup_id,
                AdsDailyMetric.campaign_id,
                MarketingAdGroup.name,
                MarketingAdGroup.status,
            )
            .order_by(func.coalesce(func.sum(AdsDailyMetric.spend), 0).desc())
        )
    ).all()

    out: list[dict] = []
    for (
        platform,
        connection_id,
        adgroup_id,
        campaign_id,
        name,
        status,
        spend,
        impressions,
        clicks,
        conversions,
        conversion_value,
    ) in rows:
        out.append(
            {
                "platform": platform,
                "connection_id": connection_id,
                "adgroup_id": adgroup_id,
                "campaign_id": campaign_id,
                "name": name,
                "status": status,
                **_ads_metrics(
                    spend, impressions, clicks, conversions, conversion_value,
                    cost_per_conversion=True,
                    conversion_rate=True,
                ),
            }
        )
    return out


# ════════════════════════════════════════════════════════════════════════════
# Website Analytics (GA4 / GSC)
# ════════════════════════════════════════════════════════════════════════════
async def analytics(
    session: AsyncSession,
    company_id: int,
    date_from: date,
    date_to: date,
    *,
    top_pages_limit: int = 20,
    top_queries_limit: int = 20,
) -> dict:
    """GA4 + GSC read from ``analytics_daily``.

    Totals are summed ONLY over ``dimension_type='total'`` rows (A11) — never by
    summing channel/page/query rows. Traffic sources come from ``'channel'``, top
    pages from ``'page'``, GSC queries from ``'query'``. GSC ratios (CTR/position)
    are ratio-of-sums where additive: site CTR = ``SUM(clicks)/SUM(impressions)``;
    average position is weighted by impressions (its natural denominator).
    """
    # GA4 totals (dimension_type='total', source='ga4').
    ga4_total = (
        await session.execute(
            select(
                func.coalesce(func.sum(AnalyticsDaily.sessions), 0),
                func.coalesce(func.sum(AnalyticsDaily.users), 0),
                func.coalesce(func.sum(AnalyticsDaily.new_users), 0),
                func.coalesce(func.sum(AnalyticsDaily.engaged_sessions), 0),
                func.coalesce(func.sum(AnalyticsDaily.key_events), 0),
                # Portable "any sampled?" — max of the boolean cast (PG + SQLite).
                func.coalesce(
                    func.max(func.cast(AnalyticsDaily.is_sampled, Integer)), 0
                ),
            ).where(
                AnalyticsDaily.company_id == company_id,
                AnalyticsDaily.source == "ga4",
                AnalyticsDaily.dimension_type == "total",
                AnalyticsDaily.date >= date_from,
                AnalyticsDaily.date <= date_to,
            )
        )
    ).one()
    sessions, users, new_users, engaged_sessions, key_events, is_sampled = ga4_total
    # "all golden?" over ALL GA4 rows in the window (H3): the "(other)" overflow
    # (dataLossFromOtherRow) is recorded on the channel/page breakdown rows, NOT the
    # date-only total rows — so checking only 'total' would never surface it. 0 if any
    # GA4 row this window overflowed / wasn't finalized.
    is_golden = (
        await session.execute(
            select(func.coalesce(func.min(func.cast(AnalyticsDaily.is_data_golden, Integer)), 1)).where(
                AnalyticsDaily.company_id == company_id,
                AnalyticsDaily.source == "ga4",
                AnalyticsDaily.date >= date_from,
                AnalyticsDaily.date <= date_to,
            )
        )
    ).scalar_one()
    sessions = _int(sessions)
    engaged_sessions = _int(engaged_sessions)
    ga4_totals = {
        "sessions": sessions,
        "users": _int(users),
        "new_users": _int(new_users),
        "engaged_sessions": engaged_sessions,
        # H7: key_events IS GA4's conversion metric (no separate `conversions` — that
        # is for ad platforms; carrying both was a duplicated, double-count-inviting value).
        "key_events": q6(key_events or 0),
        # Engagement rate as ratio-of-sums (engaged / total sessions).
        "engagement_rate": _ratio(engaged_sessions, sessions),
        "is_sampled": bool(is_sampled),
        "is_data_golden": bool(is_golden),
    }

    # GA4 daily sessions/users trend (totals only).
    ga4_series_rows = (
        await session.execute(
            select(
                AnalyticsDaily.date,
                func.coalesce(func.sum(AnalyticsDaily.sessions), 0),
                func.coalesce(func.sum(AnalyticsDaily.users), 0),
            )
            .where(
                AnalyticsDaily.company_id == company_id,
                AnalyticsDaily.source == "ga4",
                AnalyticsDaily.dimension_type == "total",
                AnalyticsDaily.date >= date_from,
                AnalyticsDaily.date <= date_to,
            )
            .group_by(AnalyticsDaily.date)
            .order_by(AnalyticsDaily.date)
        )
    ).all()
    ga4_series = [
        {"date": d, "sessions": _int(s), "users": _int(u)}
        for d, s, u in ga4_series_rows
    ]

    # Traffic sources (channel breakdown).
    channel_rows = (
        await session.execute(
            select(
                AnalyticsDaily.dimension_value,
                func.coalesce(func.sum(AnalyticsDaily.sessions), 0),
                func.coalesce(func.sum(AnalyticsDaily.users), 0),
            )
            .where(
                AnalyticsDaily.company_id == company_id,
                AnalyticsDaily.source == "ga4",
                AnalyticsDaily.dimension_type == "channel",
                AnalyticsDaily.date >= date_from,
                AnalyticsDaily.date <= date_to,
            )
            .group_by(AnalyticsDaily.dimension_value)
            .order_by(func.coalesce(func.sum(AnalyticsDaily.sessions), 0).desc())
        )
    ).all()
    traffic_sources = [
        {"channel": dim, "sessions": _int(s), "users": _int(u)}
        for dim, s, u in channel_rows
    ]

    # Top pages.
    page_rows = (
        await session.execute(
            select(
                AnalyticsDaily.dimension_value,
                func.coalesce(func.sum(AnalyticsDaily.sessions), 0),
                func.coalesce(func.sum(AnalyticsDaily.users), 0),
            )
            .where(
                AnalyticsDaily.company_id == company_id,
                AnalyticsDaily.source == "ga4",
                AnalyticsDaily.dimension_type == "page",
                AnalyticsDaily.date >= date_from,
                AnalyticsDaily.date <= date_to,
            )
            .group_by(AnalyticsDaily.dimension_value)
            .order_by(func.coalesce(func.sum(AnalyticsDaily.sessions), 0).desc())
            .limit(top_pages_limit)
        )
    ).all()
    top_pages = [
        {"page": dim, "sessions": _int(s), "users": _int(u)}
        for dim, s, u in page_rows
    ]

    # GSC totals (source='gsc', dimension_type='total').
    gsc_total = (
        await session.execute(
            select(
                func.coalesce(func.sum(AnalyticsDaily.clicks), 0),
                func.coalesce(func.sum(AnalyticsDaily.impressions), 0),
                # Impression-weighted position numerator (Σ position*impressions).
                func.coalesce(
                    func.sum(
                        func.cast(AnalyticsDaily.position, Numeric(18, 6))
                        * func.cast(AnalyticsDaily.impressions, Numeric(18, 6))
                    ),
                    0,
                ),
            ).where(
                AnalyticsDaily.company_id == company_id,
                AnalyticsDaily.source == "gsc",
                AnalyticsDaily.dimension_type == "total",
                AnalyticsDaily.date >= date_from,
                AnalyticsDaily.date <= date_to,
            )
        )
    ).one()
    gsc_clicks, gsc_impressions, gsc_position_weighted = gsc_total
    gsc_clicks = _int(gsc_clicks)
    gsc_impressions = _int(gsc_impressions)
    gsc_totals = {
        "clicks": gsc_clicks,
        "impressions": gsc_impressions,
        "ctr": _ratio(gsc_clicks, gsc_impressions),
        # Average position weighted by impressions (ratio-of-sums, A5).
        "position": _ratio(gsc_position_weighted, gsc_impressions),
    }

    # Top GSC queries.
    query_rows = (
        await session.execute(
            select(
                AnalyticsDaily.dimension_value,
                func.coalesce(func.sum(AnalyticsDaily.clicks), 0),
                func.coalesce(func.sum(AnalyticsDaily.impressions), 0),
                func.coalesce(
                    func.sum(
                        func.cast(AnalyticsDaily.position, Numeric(18, 6))
                        * func.cast(AnalyticsDaily.impressions, Numeric(18, 6))
                    ),
                    0,
                ),
            )
            .where(
                AnalyticsDaily.company_id == company_id,
                AnalyticsDaily.source == "gsc",
                AnalyticsDaily.dimension_type == "query",
                AnalyticsDaily.date >= date_from,
                AnalyticsDaily.date <= date_to,
            )
            .group_by(AnalyticsDaily.dimension_value)
            .order_by(func.coalesce(func.sum(AnalyticsDaily.clicks), 0).desc())
            .limit(top_queries_limit)
        )
    ).all()
    gsc_queries = []
    for dim, clicks, impressions, pos_weighted in query_rows:
        cl = _int(clicks)
        imp = _int(impressions)
        gsc_queries.append(
            {
                "query": dim,
                "clicks": cl,
                "impressions": imp,
                "ctr": _ratio(cl, imp),
                "position": _ratio(pos_weighted, imp),
            }
        )

    # Top GSC pages (dimension_type='page') — same ratio-of-sums shape as queries,
    # ordered by clicks. Position is impression-weighted (A5).
    gsc_page_rows = (
        await session.execute(
            select(
                AnalyticsDaily.dimension_value,
                func.coalesce(func.sum(AnalyticsDaily.clicks), 0),
                func.coalesce(func.sum(AnalyticsDaily.impressions), 0),
                func.coalesce(
                    func.sum(
                        func.cast(AnalyticsDaily.position, Numeric(18, 6))
                        * func.cast(AnalyticsDaily.impressions, Numeric(18, 6))
                    ),
                    0,
                ),
            )
            .where(
                AnalyticsDaily.company_id == company_id,
                AnalyticsDaily.source == "gsc",
                AnalyticsDaily.dimension_type == "page",
                AnalyticsDaily.date >= date_from,
                AnalyticsDaily.date <= date_to,
            )
            .group_by(AnalyticsDaily.dimension_value)
            .order_by(func.coalesce(func.sum(AnalyticsDaily.clicks), 0).desc())
            .limit(top_pages_limit)
        )
    ).all()
    gsc_pages = []
    for dim, clicks, impressions, pos_weighted in gsc_page_rows:
        cl = _int(clicks)
        imp = _int(impressions)
        gsc_pages.append(
            {
                "page": dim,
                "clicks": cl,
                "impressions": imp,
                "ctr": _ratio(cl, imp),
                "position": _ratio(pos_weighted, imp),
            }
        )

    return {
        "ga4_totals": ga4_totals,
        "ga4_series": ga4_series,
        "traffic_sources": traffic_sources,
        "top_pages": top_pages,
        "gsc_totals": gsc_totals,
        "gsc_queries": gsc_queries,
        "gsc_pages": gsc_pages,
        "ga4_configured": sessions > 0 or bool(ga4_series),
        "gsc_configured": gsc_impressions > 0 or bool(gsc_queries) or bool(gsc_pages),
    }


# ════════════════════════════════════════════════════════════════════════════
# Site Health — latest snapshots + trend
# ════════════════════════════════════════════════════════════════════════════
async def site_health(
    session: AsyncSession,
    company_id: int,
    date_from: date,
    date_to: date,
) -> dict:
    """Latest PageSpeed snapshot per (url, strategy) + the score trend.

    "Latest" is the most recent ``captured_date`` (ties broken by ``fetched_at``)
    so a re-run that restates a day doesn't show two cards. The trend returns all
    snapshots in the window for a small line chart.
    """
    all_rows = (
        await session.execute(
            select(SiteHealthSnapshot)
            .where(
                SiteHealthSnapshot.company_id == company_id,
                SiteHealthSnapshot.captured_date >= date_from,
                SiteHealthSnapshot.captured_date <= date_to,
            )
            .order_by(
                SiteHealthSnapshot.captured_date.desc(),
                SiteHealthSnapshot.fetched_at.desc(),
            )
        )
    ).scalars().all()

    latest: dict[tuple[str, str], dict] = {}
    trend: list[dict] = []
    for s in all_rows:
        snap = {
            "url": s.url,
            "strategy": s.strategy,
            "captured_date": s.captured_date,
            "performance_score": s.performance_score,
            "seo_score": s.seo_score,
            "accessibility_score": s.accessibility_score,
            "best_practices_score": s.best_practices_score,
            "lcp_ms": s.lcp_ms,
            "cls": s.cls,
            "inp_ms": s.inp_ms,
        }
        trend.append(snap)
        key = (s.url, s.strategy)
        if key not in latest:  # rows already sorted newest-first
            latest[key] = snap

    # Trend chronological for charting.
    trend.sort(key=lambda r: r["captured_date"])
    return {"latest": list(latest.values()), "trend": trend}


# ════════════════════════════════════════════════════════════════════════════
# Daily breakdown tables (per-day)
# ════════════════════════════════════════════════════════════════════════════
async def breakdown(
    session: AsyncSession,
    company_id: int,
    date_from: date,
    date_to: date,
    *,
    entity_level: str = "account",
) -> list[dict]:
    """Per-day per-platform table (the vendor's "Daily Breakdown").

    One row per (date, platform). Ratios are per-row ratio-of-sums (A5). Ordered
    by date descending (most recent first, as the vendor table shows).
    """
    rows = (
        await session.execute(
            select(
                AdsDailyMetric.date,
                AdsDailyMetric.platform,
                # FE-1: group by currency too so each (date, platform) row carries its
                # own currency — the breakdown is the only paid panel rendered under a
                # multi-currency client, so it must label money correctly (mirrors
                # allocation's per-slice currency), not with one client-wide currency.
                AdsDailyMetric.currency,
                func.coalesce(func.sum(AdsDailyMetric.spend), 0),
                func.coalesce(func.sum(AdsDailyMetric.impressions), 0),
                func.coalesce(func.sum(AdsDailyMetric.clicks), 0),
                func.coalesce(func.sum(AdsDailyMetric.conversions), 0),
                func.coalesce(func.sum(AdsDailyMetric.conversion_value), 0),
            )
            .where(
                AdsDailyMetric.company_id == company_id,
                AdsDailyMetric.entity_level == entity_level,
                AdsDailyMetric.date >= date_from,
                AdsDailyMetric.date <= date_to,
            )
            .group_by(AdsDailyMetric.date, AdsDailyMetric.platform, AdsDailyMetric.currency)
            .order_by(AdsDailyMetric.date.desc(), AdsDailyMetric.platform)
        )
    ).all()

    out: list[dict] = []
    for d, platform, currency, spend, impressions, clicks, conversions, conversion_value in rows:
        out.append(
            {
                "date": d,
                "platform": platform,
                "currency": currency,
                **_ads_metrics(
                    spend, impressions, clicks, conversions, conversion_value,
                    cost_per_conversion=True,
                ),
            }
        )
    return out


# ════════════════════════════════════════════════════════════════════════════
# Budget pacing — BudgetPeriod vs MTD spend → projected month-end
# ════════════════════════════════════════════════════════════════════════════
async def budget_pacing(
    session: AsyncSession,
    company_id: int,
    as_of: date,
) -> list[dict]:
    """Per-connection month-to-date spend vs ``budget_periods`` → pace badge.

    For the calendar month containing ``as_of``: MTD spend (account-level facts),
    the configured budget, a linear month-end projection
    (``mtd / days_elapsed * days_in_month``), and an over/under-pace flag. ÷0 days
    is impossible (``as_of.day`` ≥ 1). No budget row → ``budget=None``, projection
    still returned so the UI can show spend even without a target.
    """
    import calendar

    month_start = as_of.replace(day=1)
    # First day of the NEXT month — used for a half-open [month_start, next_month)
    # budget match so a row stored with a non-first day still pairs to its month
    # (BUDGET-PERIODS: exact period_month == month_start silently missed such rows).
    next_month = (
        date(as_of.year + 1, 1, 1)
        if as_of.month == 12
        else date(as_of.year, as_of.month + 1, 1)
    )
    days_in_month = calendar.monthrange(as_of.year, as_of.month)[1]
    days_elapsed = as_of.day

    # MTD spend per connection (account level only — A2).
    spend_rows = (
        await session.execute(
            select(
                AdsDailyMetric.connection_id,
                AdsDailyMetric.platform,
                func.coalesce(func.sum(AdsDailyMetric.spend), 0),
            )
            .where(
                AdsDailyMetric.company_id == company_id,
                AdsDailyMetric.entity_level == "account",
                AdsDailyMetric.date >= month_start,
                AdsDailyMetric.date <= as_of,
            )
            .group_by(AdsDailyMetric.connection_id, AdsDailyMetric.platform)
        )
    ).all()
    spend_by_conn: dict[int, tuple[str, Decimal]] = {
        conn_id: (platform, q6(spend or 0))
        for conn_id, platform, spend in spend_rows
    }

    # Budgets for this month, joined to the connection for company scoping.
    budget_rows = (
        await session.execute(
            select(
                BudgetPeriod.connection_id,
                BudgetPeriod.amount,
                BudgetPeriod.currency,
                PlatformConnection.platform,
                PlatformConnection.display_name,
                PlatformConnection.currency,
            )
            .join(
                PlatformConnection,
                PlatformConnection.id == BudgetPeriod.connection_id,
            )
            .where(
                PlatformConnection.company_id == company_id,
                BudgetPeriod.period_month >= month_start,
                BudgetPeriod.period_month < next_month,
            )
        )
    ).all()

    out: list[dict] = []
    seen: set[int] = set()
    for conn_id, amount, budget_ccy, platform, display_name, conn_ccy in budget_rows:
        # The half-open month match can return >1 budget row for a connection if two
        # rows fall in the same month (schema permits distinct days) — emit one pace
        # row per connection (first wins) rather than double-listing it.
        if conn_id in seen:
            continue
        seen.add(conn_id)
        _, mtd = spend_by_conn.get(conn_id, (platform, Decimal(0)))
        out.append(
            _pace_row(
                conn_id, platform, display_name, q6(amount), budget_ccy or conn_ccy,
                mtd, days_elapsed, days_in_month,
            )
        )

    # Connections that spent but have no budget row → still surface the spend.
    for conn_id, (platform, mtd) in spend_by_conn.items():
        if conn_id in seen:
            continue
        out.append(
            _pace_row(
                conn_id, platform, None, None, None,
                mtd, days_elapsed, days_in_month,
            )
        )

    out.sort(key=lambda r: r["mtd_spend"], reverse=True)
    return out


def _pace_row(
    connection_id: int,
    platform: str,
    display_name: str | None,
    budget: Decimal | None,
    currency: str | None,
    mtd_spend: Decimal,
    days_elapsed: int,
    days_in_month: int,
) -> dict:
    """Assemble one budget-pacing row with a linear month-end projection."""
    projected = q6(mtd_spend / days_elapsed * days_in_month) if days_elapsed else None
    pace_ratio: Decimal | None = None
    over_pace: bool | None = None
    if budget and budget > 0 and projected is not None:
        pace_ratio = _ratio(projected, budget)
        over_pace = projected > budget
    return {
        "connection_id": connection_id,
        "platform": platform,
        "display_name": display_name,
        "budget": budget,
        "currency": currency,
        "mtd_spend": mtd_spend,
        "projected_month_end": projected,
        "days_elapsed": days_elapsed,
        "days_in_month": days_in_month,
        "pace_ratio": pace_ratio,
        "over_pace": over_pace,
    }


# ════════════════════════════════════════════════════════════════════════════
# Sync status — truthful "Live / Updated Nm ago"
# ════════════════════════════════════════════════════════════════════════════
async def sync_status(
    session: AsyncSession,
    company_id: int,
) -> list[dict]:
    """Per-connection freshness: ``last_synced_at``/status/``last_error`` plus the
    latest ``marketing_sync_runs`` row — the truthful freshness signal that
    replaces the vendor's decorative "Live" dot.

    The "last successful sync" timestamp comes from the connection's
    ``last_synced_at`` (set by ingest on success); the latest run row carries the
    most recent attempt's status/rows/error so a *failed* last attempt reads as
    amber even when an older success exists.
    """
    connections = (
        await session.execute(
            select(PlatformConnection)
            .where(PlatformConnection.company_id == company_id)
            .order_by(PlatformConnection.platform, PlatformConnection.id)
        )
    ).scalars().all()

    out: list[dict] = []
    for conn in connections:
        latest_run = (
            await session.execute(
                select(MarketingSyncRun)
                .where(MarketingSyncRun.connection_id == conn.id)
                .order_by(
                    MarketingSyncRun.started_at.desc(), MarketingSyncRun.id.desc()
                )
                .limit(1)
            )
        ).scalar_one_or_none()

        out.append(
            {
                "connection_id": conn.id,
                "platform": conn.platform,
                "display_name": conn.display_name,
                "external_account_id": conn.external_account_id,
                "status": conn.status,
                "last_synced_at": conn.last_synced_at,
                "last_error": conn.last_error,
                "failure_count": conn.failure_count,
                "reporting_timezone": conn.reporting_timezone,
                "currency": conn.currency,
                "latest_run": _run_summary(latest_run) if latest_run else None,
            }
        )
    return out


def _run_summary(run: MarketingSyncRun) -> dict:
    return {
        "run_type": run.run_type,
        "status": run.status,
        "rows_upserted": run.rows_upserted,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "error_class": run.error_class,
        "window_start": run.window_start,
        "window_end": run.window_end,
    }


__all__ = [
    "series",
    "allocation",
    "day_of_week",
    "campaigns",
    "adgroups",
    "analytics",
    "site_health",
    "breakdown",
    "budget_pacing",
    "sync_status",
]
