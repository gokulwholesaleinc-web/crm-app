"""Read-side aggregation — ratios as ratio-of-sums, computed in SQL (A5).

KPIs and rollups are ``SUM(numerator) / SUM(denominator)`` — never the average of
daily ratios, which silently over-weights low-volume days (A5). Divide-by-zero
yields ``None`` so the UI renders "New"/an em-dash, never ``Infinity%``/``NaN%``.
Every aggregation filters to exactly one ``entity_level`` so mixed-grain rows can't
double-count (A2).

This module is the foundation seam the C2 gating test pins; the full per-tab
endpoint surface (series, allocation, day-of-week, campaigns, analytics,
site-health) layers on top of these same primitives and the explicit-keyed cache.

Blended cross-platform KPIs are withheld for multi-currency clients by default
(A9 / Q11): raw account-currency amounts are never summed across currencies until
FX is scoped and ``MKTG_MULTI_CURRENCY`` is enabled.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import AdsDailyMetric, PlatformConnection
from .money import q6

# Spend-bearing platforms — currency mismatch across these is what withholds
# blended KPIs (GA4/GSC/PageSpeed carry no spend, so their currency is irrelevant).
_AD_PLATFORMS = ("google_ads", "meta_ads", "instagram", "facebook", "tiktok", "linkedin")


def _ratio(numerator, denominator) -> Decimal | None:
    """Ratio-of-sums with a safe zero/None denominator → ``None`` (render "New")."""
    if not denominator:
        return None
    return (Decimal(numerator) / Decimal(denominator)).quantize(Decimal("0.000001"))


async def distinct_currencies(session: AsyncSession, company_id: int) -> set[str]:
    """The set of account currencies across a client's spend-bearing connections."""
    rows = await session.execute(
        select(PlatformConnection.currency)
        .where(
            PlatformConnection.company_id == company_id,
            PlatformConnection.currency.isnot(None),
            PlatformConnection.platform.in_(_AD_PLATFORMS),
        )
        .distinct()
    )
    return {c for (c,) in rows.all() if c}


def blended_withhold_reason(
    currencies: set[str], *, multi_currency_enabled: bool
) -> str | None:
    """``"multi_currency"`` when blended KPIs must be withheld, else ``None`` (A9)."""
    distinct = {c for c in currencies if c}
    if len(distinct) > 1 and not multi_currency_enabled:
        return "multi_currency"
    return None


async def ads_overview(
    session: AsyncSession,
    company_id: int,
    date_from: date,
    date_to: date,
    *,
    entity_level: str = "account",
) -> dict:
    """Spend/clicks/impressions/conversions sums + ratio-of-sums KPIs for a window.

    Filters to one ``entity_level`` (A2). All ratios are ratio-of-sums (A5); a zero
    denominator → ``None`` (UI shows "New"/em-dash, never Infinity/NaN).
    """
    row = (
        await session.execute(
            select(
                func.coalesce(func.sum(AdsDailyMetric.spend), 0),
                func.coalesce(func.sum(AdsDailyMetric.impressions), 0),
                func.coalesce(func.sum(AdsDailyMetric.clicks), 0),
                func.coalesce(func.sum(AdsDailyMetric.conversions), 0),
                func.coalesce(func.sum(AdsDailyMetric.conversion_value), 0),
            ).where(
                AdsDailyMetric.company_id == company_id,
                AdsDailyMetric.entity_level == entity_level,
                AdsDailyMetric.date >= date_from,
                AdsDailyMetric.date <= date_to,
            )
        )
    ).one()
    spend, impressions, clicks, conversions, conversion_value = row
    spend = q6(spend)
    conversions = q6(conversions)
    conversion_value = q6(conversion_value)
    impressions = int(impressions)
    clicks = int(clicks)
    return {
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
