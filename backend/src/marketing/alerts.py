"""Marketing anomaly alert producers (B4) — DORMANT until ``MKTG_ALERTS_ENABLED``.

Phase-2 ships exactly one producer: **stale_sync** (CRITICAL-2). The
``marketing_alerts`` table existed since migration 056 with a ``stale_sync``
alert_type but had no producer — so a connection that keeps reading ``active``
while never actually refreshing (a permanently-throttled or silently-degraded
source) raised no alarm. Truthful freshness is the #1 vendor-dashboard sin we
fix, so after the daily run :func:`detect_stale_syncs` opens a deduplicated
alert per such connection and auto-resolves it once the connection recovers.

Dedup + suppression live here, not in the schema (per the model docstring): one
open alert per connection via the ``(company_id, dedup_key)`` unique constraint.
The upsert is a portable SELECT-then-write (NOT ``ON CONFLICT``) so it also runs
on the SQLite test harness; the daily cron is ``max_instances=1`` so there is no
concurrent producer to race. stale_sync IS the failed-ingest canary, so it is
NOT subject to the B4 "suppress on failed ingest" rule that guards value-based
alerts (spend/conversions) from firing on a night the sync simply failed.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings

from .ingest import SUPPORTED_PLATFORMS
from .models import MarketingAlert, PlatformConnection

logger = logging.getLogger(__name__)

# A daily-cadence connection that has not refreshed in this long is stale. Two
# missed daily windows + slack so a single deploy spanning the cron fire time
# doesn't alarm. ``last_synced_at`` is stamped ONLY on a successful sync
# (``health.apply_success``); a run of failed/partial syncs leaves it stale.
STALE_AFTER_HOURS = 48

_ALERT_TYPE = "stale_sync"

# Statuses that don't get a stale_sync alert:
#  - disabled / needs_reauth: operator-silenced or already surfaced by their status.
#  - pending: first sync hasn't completed yet (last_synced_at NULL ⇒ would alarm on
#    day one); a never-synced connection that's actually stuck escalates to 'error'
#    (CRITICAL-2) and is surfaced that way instead.
_SKIP_STATUSES = ("disabled", "needs_reauth", "pending")


def stale_sync_dedup_key(connection_id: int) -> str:
    """The stable dedup key for a connection's stale_sync alert (one open row)."""
    return f"stale_sync:connection:{connection_id}"


async def detect_stale_syncs(
    session: AsyncSession,
    *,
    now: datetime | None = None,
    stale_after_hours: int = STALE_AFTER_HOURS,
) -> int:
    """Open/refresh a stale_sync alert per enabled connection that has not synced
    successfully within the window (or has never synced), and auto-resolve alerts
    for connections that have since recovered.

    Returns the number of alerts opened or refreshed. The caller (scheduler) gates
    this on ``MKTG_ALERTS_ENABLED``; it is safe to call directly in tests. The
    caller commits.
    """
    now = now or datetime.now(UTC)
    cutoff = now - timedelta(hours=stale_after_hours)

    conns = (
        (
            await session.execute(
                select(PlatformConnection).where(PlatformConnection.is_enabled.is_(True))
            )
        )
        .scalars()
        .all()
    )

    # All existing stale_sync alerts (resolved or open) keyed by connection for
    # O(1) lookup — re-staleness re-opens the same row rather than violating the
    # (company_id, dedup_key) unique constraint.
    existing = {
        a.connection_id: a
        for a in (
            await session.execute(
                select(MarketingAlert).where(MarketingAlert.alert_type == _ALERT_TYPE)
            )
        )
        .scalars()
        .all()
        if a.connection_id is not None
    }

    fired = 0
    for conn in conns:
        if conn.status in _SKIP_STATUSES:
            continue
        # A platform with no ingest handler (tiktok/linkedin — enum-valid but unwired)
        # can never sync, so a stale_sync alert would fire forever with no recovery
        # path. Skip anything not actually ingestible.
        if conn.platform not in SUPPORTED_PLATFORMS:
            continue
        # A phase-gated platform (meta_ads behind MKTG_META_ENABLED, organic social
        # behind MKTG_SOCIAL_ENABLED) is dark by design — the scheduler never syncs
        # it, so don't flag it as a stuck source.
        if conn.platform == "meta_ads" and not settings.MKTG_META_ENABLED:
            continue
        if conn.platform in ("instagram", "facebook") and not settings.MKTG_SOCIAL_ENABLED:
            continue
        last = conn.last_synced_at
        # Postgres returns tz-aware (DateTime(timezone=True)); the SQLite test
        # harness returns naive. Normalize so the comparison never crashes on the
        # mixed-aware case — a naive stamp is treated as UTC.
        if last is not None and last.tzinfo is None:
            last = last.replace(tzinfo=UTC)
        is_stale = last is None or last < cutoff
        alert = existing.get(conn.id)

        if is_stale:
            message = (
                f"{conn.platform} connection {conn.id} has not synced successfully "
                + (f"since {last.isoformat()}" if last else "yet")
            )
            if alert is None:
                session.add(
                    MarketingAlert(
                        company_id=conn.company_id,
                        connection_id=conn.id,
                        alert_type=_ALERT_TYPE,
                        dedup_key=stale_sync_dedup_key(conn.id),
                        severity="warning",
                        message=message,
                        metric_date=now.date(),
                        last_fired_at=now,
                        is_resolved=False,
                    )
                )
            else:
                alert.message = message
                alert.last_fired_at = now
                alert.metric_date = now.date()
                alert.is_resolved = False
            fired += 1
        elif alert is not None and not alert.is_resolved:
            # Recovered (synced within the window) — auto-resolve the open alert.
            alert.is_resolved = True

    await session.flush()
    return fired
