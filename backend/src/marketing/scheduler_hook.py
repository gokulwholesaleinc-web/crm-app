"""Daily marketing ingest hook (D1) — the scheduler entry point.

A dedicated daily ``CronTrigger`` job (NOT the 90-min ``_background_tick``, which
fires 16×/day) that, for each syncable connection, runs a short daily spend
lookback and — for ad platforms — a separate conversion-settling re-fetch (A7).

Per-connection isolation mirrors ``core/scheduler.py:_sync_google_calendars``:
each connection gets its own fresh session so one revoked token / rollback can't
poison the others, and ``run_connection_sync`` already captures per-connection
failures on a ``MarketingSyncRun`` row + transitions health rather than raising.
After a company's connections sync, its cached reads are invalidated (D4) so the
dashboard reflects fresh data immediately.

The whole job is gated by ``MKTG_ENABLED`` so it stays dormant until the feature
is switched on per the phased rollout.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from sqlalchemy import select

import src.database as db_module
from src.config import settings

from . import cache
from .ingest import run_connection_sync, settling
from .models import PlatformConnection

logger = logging.getLogger(__name__)

# Short rolling spend lookback re-fetched daily (restates recent days). The longer
# conversion-settling window is fetched separately for ad platforms (A7).
DAILY_LOOKBACK_DAYS = 3

# Statuses worth syncing: active (healthy), pending (first sync), error (transient
# retry — backoff is enforced by failure_count in the health machine). needs_reauth
# and disabled are skipped (no valid token / operator-disabled).
SYNCABLE_STATUSES = ("active", "pending", "error")


async def _syncable_connections() -> list[PlatformConnection]:
    async with db_module.async_session_maker() as session:
        rows = await session.execute(
            select(PlatformConnection).where(
                PlatformConnection.is_enabled.is_(True),
                PlatformConnection.status.in_(SYNCABLE_STATUSES),
            )
        )
        return list(rows.scalars().all())


async def _sync_one(connection_id: int, *, today: date) -> int | None:
    """Sync one connection in its own session. Returns the company_id on success
    (so the caller can invalidate that company's cache), else ``None``."""
    try:
        async with db_module.async_session_maker() as session:
            connection = await session.get(PlatformConnection, connection_id)
            if connection is None:
                return None
            daily_end = today - timedelta(days=1)
            daily_start = daily_end - timedelta(days=DAILY_LOOKBACK_DAYS - 1)
            await run_connection_sync(
                session, connection, run_type="daily",
                window_start=daily_start, window_end=daily_end,
            )
            if settling.needs_settling(connection):
                s_start, s_end = settling.settling_window(connection, today=today)
                await run_connection_sync(
                    session, connection, run_type="settling",
                    window_start=s_start, window_end=s_end,
                )
            await session.commit()
            return connection.company_id
    except Exception:
        # Belt-and-suspenders: run_connection_sync already absorbs per-connection
        # ingest errors; this guards a commit/session failure so one bad connection
        # can't abort the daily tick.
        logger.exception("[marketing_daily] connection_id=%s failed", connection_id)
        return None


async def run_daily_marketing_sync(*, today: date | None = None) -> None:
    """Daily ingest across all syncable connections (D1). No-op when disabled."""
    if not settings.MKTG_ENABLED:
        return
    today = today or date.today()
    connections = await _syncable_connections()
    if not connections:
        return

    logger.info("[marketing_daily] syncing %d connection(s)", len(connections))
    affected: set[int] = set()
    for connection in connections:
        company_id = await _sync_one(connection.id, today=today)
        if company_id is not None:
            affected.add(company_id)

    # Refresh the read cache for every touched client so the dashboard is current.
    for company_id in affected:
        await cache.invalidate(company_id)
    logger.info(
        "[marketing_daily] done — %d connection(s), %d client cache(s) invalidated",
        len(connections), len(affected),
    )
