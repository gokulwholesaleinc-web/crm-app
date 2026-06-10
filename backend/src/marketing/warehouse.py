"""Idempotent warehouse writer — the one place facts/dims/landing are upserted.

Postgres-only by design (C1): every write uses ``INSERT … ON CONFLICT … DO UPDATE``
keyed on the natural grain constraint (``NULLS NOT DISTINCT`` so account-level rows
with NULL campaign/adgroup ids de-dup, A2), restating measures so the daily
rolling-lookback re-fetch corrects late/restated conversions (A7) — never
``DO NOTHING``. Writers for one connection serialize on a ``pg_advisory_xact_lock``
so backfill + daily + settling lanes can't interleave on the same rows (D2).

Contracts:
* Inputs are the frozen ``rows.py`` dataclasses (``Decimal`` money/conversions
  already normalized by the ingest mapper — Google micros ÷ 1e6, A4/NN-8). This
  module does no parsing; it only writes.
* Each batch is de-duped to one row per grain (last wins) before the INSERT, so a
  single multi-row ``ON CONFLICT`` statement can't "affect a row a second time".
* Returns the number of rows the statement touched.

SQLite (the unit harness) cannot express ``NULLS NOT DISTINCT`` / advisory locks,
so these paths are covered by the real-PG tier (``test_warehouse_c2_pg.py``).
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Iterable, Sequence
from dataclasses import asdict
from datetime import date, datetime
from typing import Any, cast

from sqlalchemy import func, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    AdsDailyMetric,
    AnalyticsDaily,
    MarketingAdGroup,
    MarketingCampaign,
    MarketingRawPayload,
    SiteHealthSnapshot,
    SocialDailyMetric,
)
from .rows import (
    AdGroupDimRow,
    AdsDailyRow,
    AnalyticsDailyRow,
    CampaignDimRow,
    SiteHealthRow,
    SocialDailyRow,
)

# Advisory-lock namespace (int4) — keeps marketing's per-connection locks from
# colliding with any other advisory-lock user (e.g. a future scheduler singleton).
LOCK_NAMESPACE = 0x4D4B  # "MK"

# Measure columns restated on conflict, per table (grain/identity cols excluded).
_ADS_MEASURES = (
    "spend", "impressions", "clicks", "conversions",
    "conversion_value", "reach", "purchases", "currency",
)
_ANALYTICS_MEASURES = (
    "sessions", "users", "new_users", "engaged_sessions", "engagement_rate",
    "bounce_rate", "conversions", "key_events", "avg_session_duration",
    "impressions", "clicks", "ctr", "position", "is_sampled", "is_data_golden",
)
_SITE_HEALTH_MEASURES = (
    "performance_score", "seo_score", "accessibility_score",
    "best_practices_score", "lcp_ms", "cls", "inp_ms",
)


def _affected(result: Any) -> int:
    """Rows touched by a DML statement. ``AsyncSession.execute`` is typed
    ``Result`` but a DML always yields a ``CursorResult`` (which exposes rowcount)."""
    return cast("CursorResult[Any]", result).rowcount


# ── advisory locking (D2) ────────────────────────────────────────────────────
async def lock_connection(session: AsyncSession, connection_id: int) -> None:
    """Blocking ``pg_advisory_xact_lock`` for a connection — serializes its writers.

    Held until the surrounding transaction commits/rolls back. Call at the top of a
    sync lane (daily / backfill / settling) so the three can't deadlock on shared rows.
    """
    await session.execute(
        text("SELECT pg_advisory_xact_lock(:ns, :cid)"),
        {"ns": LOCK_NAMESPACE, "cid": connection_id},
    )


async def try_lock_connection(session: AsyncSession, connection_id: int) -> bool:
    """Non-blocking variant — ``True`` if acquired, ``False`` if another lane holds it.

    Lets a backfill skip a connection the daily job is mid-write on instead of blocking.
    """
    res = await session.execute(
        text("SELECT pg_try_advisory_xact_lock(:ns, :cid)"),
        {"ns": LOCK_NAMESPACE, "cid": connection_id},
    )
    return bool(res.scalar_one())


# ── fact / dim upserts ───────────────────────────────────────────────────────
def _dedupe(rows: Iterable[Any], key: Sequence[str]) -> list[dict]:
    """Collapse to one dict per grain (last wins) so a multi-row INSERT … ON
    CONFLICT never hits the same row twice within the statement."""
    out: OrderedDict[tuple, dict] = OrderedDict()
    for row in rows:
        values = asdict(row)
        out[tuple(values[k] for k in key)] = values
    return list(out.values())


async def _upsert(
    session: AsyncSession,
    model,
    rows: Iterable[Any],
    *,
    grain: Sequence[str],
    constraint: str,
    measures: Sequence[str],
    touch: str | None = "updated_at",
) -> int:
    values = _dedupe(rows, grain)
    if not values:
        return 0
    stmt = pg_insert(model).values(values)
    set_: dict[str, Any] = {col: stmt.excluded[col] for col in measures}
    if touch:
        set_[touch] = func.now()
    stmt = stmt.on_conflict_do_update(constraint=constraint, set_=set_)
    result = await session.execute(stmt)
    return _affected(result)


async def upsert_ads_daily(session: AsyncSession, rows: Iterable[AdsDailyRow]) -> int:
    """Restate ``ads_daily_metrics`` at its ``(connection, date, entity_level,
    campaign_id, adgroup_id)`` grain (NULLS NOT DISTINCT)."""
    return await _upsert(
        session, AdsDailyMetric, rows,
        grain=("connection_id", "date", "entity_level", "campaign_id", "adgroup_id"),
        constraint="uq_ads_daily_metrics_grain",
        measures=_ADS_MEASURES,
    )


async def upsert_analytics_daily(session: AsyncSession, rows: Iterable[AnalyticsDailyRow]) -> int:
    """Restate ``analytics_daily`` at its ``(connection, date, source,
    dimension_type, dimension_value)`` grain."""
    return await _upsert(
        session, AnalyticsDaily, rows,
        grain=("connection_id", "date", "source", "dimension_type", "dimension_value"),
        constraint="uq_analytics_daily_grain",
        measures=_ANALYTICS_MEASURES,
    )


async def upsert_social_daily(session: AsyncSession, rows: Iterable[SocialDailyRow]) -> int:
    """Restate ``social_daily_metrics`` at its ``(connection, date, platform,
    metric_key)`` grain (Phase 4)."""
    return await _upsert(
        session, SocialDailyMetric, rows,
        grain=("connection_id", "date", "platform", "metric_key"),
        constraint="uq_social_daily_metrics_grain",
        measures=("value",),
    )


async def upsert_site_health(session: AsyncSession, rows: Iterable[SiteHealthRow]) -> int:
    """Restate ``site_health_snapshots`` at ``(connection, captured_date, strategy,
    url)``. No TimestampMixin → ``fetched_at`` carries the freshness."""
    return await _upsert(
        session, SiteHealthSnapshot, rows,
        grain=("connection_id", "captured_date", "strategy", "url"),
        constraint="uq_site_health_snapshots_grain",
        measures=_SITE_HEALTH_MEASURES,
        touch="fetched_at",
    )


async def upsert_campaigns(session: AsyncSession, rows: Iterable[CampaignDimRow]) -> int:
    """Upsert the ``marketing_campaigns`` dim (name + current status, A3)."""
    return await _upsert(
        session, MarketingCampaign, rows,
        grain=("connection_id", "campaign_id"),
        constraint="uq_marketing_campaigns_identity",
        measures=("name", "status", "raw_status"),
    )


async def upsert_adgroups(session: AsyncSession, rows: Iterable[AdGroupDimRow]) -> int:
    """Upsert the ``marketing_ad_groups`` dim (A3)."""
    return await _upsert(
        session, MarketingAdGroup, rows,
        grain=("connection_id", "adgroup_id"),
        constraint="uq_marketing_ad_groups_identity",
        measures=("campaign_id", "name", "status"),
    )


# ── landing layer (A1) ───────────────────────────────────────────────────────
async def insert_raw_payload(
    session: AsyncSession,
    *,
    connection_id: int,
    platform: str,
    endpoint: str,
    window_start: date,
    window_end: date,
    request_fingerprint: str,
    payload: dict,
    row_count: int | None = None,
    fetched_at: datetime | None = None,
) -> int:
    """Land one raw API response (JSONB) — the re-derivation hedge.

    Idempotent on ``(connection, endpoint, window_start, window_end, fetched_at)``:
    re-landing the identical response is a no-op, never a duplicate.
    """
    values: dict[str, Any] = {
        "connection_id": connection_id,
        "platform": platform,
        "endpoint": endpoint,
        "window_start": window_start,
        "window_end": window_end,
        "request_fingerprint": request_fingerprint,
        "payload": payload,
        "row_count": row_count,
    }
    if fetched_at is not None:
        values["fetched_at"] = fetched_at
    stmt = pg_insert(MarketingRawPayload).values(**values)
    stmt = stmt.on_conflict_do_nothing(constraint="uq_marketing_raw_payloads_key")
    result = await session.execute(stmt)
    return _affected(result)


async def prune_raw_payloads(
    session: AsyncSession, connection_id: int, keep_days: int = 30
) -> int:
    """Prune landing history (A1): keep the latest payload per
    ``(connection, endpoint, window)`` forever, drop the rest older than
    ``keep_days``. Run nightly after ingest."""
    result = await session.execute(
        text(
            """
            DELETE FROM marketing_raw_payloads p
            WHERE p.connection_id = :cid
              AND p.fetched_at < now() - make_interval(days => :days)
              AND p.id <> (
                  SELECT q.id FROM marketing_raw_payloads q
                  WHERE q.connection_id = p.connection_id
                    AND q.endpoint = p.endpoint
                    AND q.window_start = p.window_start
                    AND q.window_end = p.window_end
                  ORDER BY q.fetched_at DESC, q.id DESC
                  LIMIT 1
              )
            """
        ),
        {"cid": connection_id, "days": keep_days},
    )
    return _affected(result)
