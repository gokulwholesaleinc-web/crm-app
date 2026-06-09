"""Throttled 13-month first-connect backfill lane (D2 / E8).

Runs OFF the daily job and OFF the Gmail/Calendar tick. Serializes a connection's
writers with ``warehouse.try_lock_connection`` (skip if another lane holds it),
bounded by per-platform retention (E8) and a per-run chunk budget so one
connection can't exhaust the daily quota in a single pass. Resumable: the
backfill walks BACKWARDS from yesterday in fixed-size chunks; the earliest day
already in the warehouse is the watermark, so re-invocation continues where it
left off and stops at the retention floor.

Pure planning here (window math + the resumable chunk plan); the actual fetch is
the same ``run_connection_sync`` path with ``run_type='backfill'`` (DRY).
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import AdsDailyMetric, AnalyticsDaily, PlatformConnection

# Per-platform retention floors in days (E8): how far back we may legally pull.
# Google Ads & Meta ~37 months; GSC 16 months. Others default to ~13mo target.
_RETENTION_DAYS = {
    "google_ads": 37 * 30,
    "meta_ads": 37 * 30,
    "instagram": 90,  # IG insights ~90-day retention
    "facebook": 37 * 30,
    "gsc": 16 * 30,
    "ga4": 14 * 30,  # GA4 default data retention; target ≥13mo for YoY
}
# Target depth when a platform isn't capped harder (≈13-month rolling, D2).
_DEFAULT_TARGET_DAYS = 400
# One backfill invocation pulls at most this many days (quota budget, D3).
DEFAULT_CHUNK_DAYS = 30


def retention_floor(connection: PlatformConnection, *, today: date) -> date:
    """Earliest date this platform's backfill may legally reach (E8)."""
    cap = _RETENTION_DAYS.get(connection.platform, _DEFAULT_TARGET_DAYS)
    depth = min(cap, _DEFAULT_TARGET_DAYS) if connection.platform in ("ga4",) else cap
    return today - timedelta(days=depth)


async def _earliest_fact_date(session: AsyncSession, connection: PlatformConnection) -> date | None:
    """The earliest day already in the warehouse for this connection (the
    resumable watermark). Ads vs analytics live in different fact tables."""
    if connection.platform in ("ga4", "gsc"):
        stmt = select(func.min(AnalyticsDaily.date)).where(AnalyticsDaily.connection_id == connection.id)
    else:
        stmt = select(func.min(AdsDailyMetric.date)).where(AdsDailyMetric.connection_id == connection.id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def next_backfill_window(
    session: AsyncSession,
    connection: PlatformConnection,
    *,
    today: date,
    chunk_days: int = DEFAULT_CHUNK_DAYS,
) -> tuple[date, date] | None:
    """The next chunk to backfill, walking backwards from the watermark.

    Returns ``(start, end)`` for the next ≤``chunk_days`` slice older than what's
    already stored, clamped to the retention floor — or ``None`` when the
    connection is already backfilled to the floor (nothing left to do).
    """
    floor = retention_floor(connection, today=today)
    earliest = await _earliest_fact_date(session, connection)

    # No data yet → start the most-recent chunk (yesterday backwards).
    if earliest is None:
        end = today - timedelta(days=1)
    else:
        if earliest <= floor:
            return None  # already at the retention floor — done
        end = earliest - timedelta(days=1)

    if end < floor:
        return None
    start = max(floor, end - timedelta(days=chunk_days - 1))
    return start, end


def is_backfillable(connection: PlatformConnection) -> bool:
    """PageSpeed is snapshot-only (no historical backfill); everything else is."""
    return connection.platform != "pagespeed"
