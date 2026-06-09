"""Backfill lane (D2) on the real-PG tier — window math, resumability, driver.

Covers the pure planning (``retention_floor`` / ``next_backfill_window`` walking
backwards from the fact watermark, clamped to the retention floor) and the
resumable, lock-aware driver (``run_connection_backfill``): chunk budget,
skip-when-locked (another writer lane holds the advisory lock), stop-at-floor, and
the not-backfillable PageSpeed short-circuit. The driver re-uses the proven
``run_connection_sync`` path with ``run_type='backfill'`` (DRY).
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import src.marketing as marketing_pkg
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker
from src.companies.models import Company
from src.config import settings
from src.marketing import warehouse
from src.marketing.ingest import backfill
from src.marketing.models import AdsDailyMetric, AnalyticsDaily, MarketingSyncRun, PlatformConnection

pytestmark = pytest.mark.pg

_FIXTURES = Path(marketing_pkg.__file__).parent / "fixtures"
TODAY = date(2026, 7, 1)


# ── pure planning ────────────────────────────────────────────────────────────
def test_retention_floor_per_platform():
    def _floor(platform: str) -> date:
        conn = PlatformConnection(
            company_id=1, platform=platform, external_account_id="x",
            credential_mode="agency_oauth", status="active",
        )
        return backfill.retention_floor(conn, today=TODAY)

    assert _floor("google_ads") == TODAY - timedelta(days=37 * 30)
    assert _floor("gsc") == TODAY - timedelta(days=16 * 30)
    # GA4 is clamped to the ~13-month target even though its retention is longer.
    assert _floor("ga4") == TODAY - timedelta(days=400)


def test_is_backfillable():
    def _c(platform: str) -> PlatformConnection:
        return PlatformConnection(
            company_id=1, platform=platform, external_account_id="x",
            credential_mode="agency_oauth", status="active",
        )

    assert backfill.is_backfillable(_c("pagespeed")) is False
    assert backfill.is_backfillable(_c("google_ads")) is True
    assert backfill.is_backfillable(_c("ga4")) is True


async def _seed_conn(session, platform="google_ads") -> tuple[Company, PlatformConnection]:
    company = Company(name="Backfill Co", status="customer")
    session.add(company)
    await session.flush()
    conn = PlatformConnection(
        company_id=company.id, platform=platform, external_account_id="8328675647",
        credential_mode="mcc_link", currency="USD", status="active",
        manager_account_id="8328675647",
    )
    session.add(conn)
    await session.flush()
    await session.commit()
    return company, conn


async def _seed_ads_fact(session, conn, on_date: date) -> None:
    session.add(
        AdsDailyMetric(
            connection_id=conn.id, company_id=conn.company_id, platform=conn.platform,
            date=on_date, entity_level="account",
            spend=Decimal("1"), impressions=1, clicks=1,
            conversions=Decimal("0"), conversion_value=Decimal("0"),
        )
    )
    await session.commit()


async def test_next_window_no_data_starts_most_recent_chunk(pg_session):
    _company, conn = await _seed_conn(pg_session)
    window = await backfill.next_backfill_window(pg_session, conn, today=TODAY, chunk_days=30)
    assert window == (TODAY - timedelta(days=30), TODAY - timedelta(days=1))


async def test_next_window_resumes_from_watermark(pg_session):
    _company, conn = await _seed_conn(pg_session)
    await _seed_ads_fact(pg_session, conn, date(2026, 3, 15))
    window = await backfill.next_backfill_window(pg_session, conn, today=TODAY, chunk_days=30)
    # walks backwards from the earliest fact (2026-03-15) → ends the day before it
    # (03-14) and spans 30 inclusive days back to 02-13.
    assert window == (date(2026, 2, 13), date(2026, 3, 14))


async def test_next_window_resumes_from_analytics_watermark(pg_session):
    # GA4/GSC read the analytics_daily watermark, not ads_daily_metrics.
    _company, conn = await _seed_conn(pg_session, platform="ga4")
    pg_session.add(
        AnalyticsDaily(
            connection_id=conn.id, company_id=conn.company_id, source="ga4",
            date=date(2026, 6, 10), dimension_type="total", dimension_value="", sessions=5,
        )
    )
    await pg_session.commit()
    window = await backfill.next_backfill_window(pg_session, conn, today=TODAY, chunk_days=30)
    assert window is not None and window[1] == date(2026, 6, 9)


async def test_next_window_none_at_retention_floor(pg_session):
    _company, conn = await _seed_conn(pg_session)
    floor = backfill.retention_floor(conn, today=TODAY)
    await _seed_ads_fact(pg_session, conn, floor)  # earliest fact already at the floor
    assert await backfill.next_backfill_window(pg_session, conn, today=TODAY) is None


# ── driver ───────────────────────────────────────────────────────────────────
class _FixtureGoogleSeam:
    def __init__(self, payload: dict[str, Any]):
        self._payload = payload

    async def post(self, url: str, json: dict[str, Any], *, headers: dict[str, str] | None = None) -> list[Any]:
        query = json.get("query", "") if isinstance(json, dict) else ""
        if "FROM ad_group" in query:
            return self._payload.get("adgroup_batches", [])
        return self._payload.get("campaign_batches", [])

    async def get(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._payload


def _google_seam() -> _FixtureGoogleSeam:
    return _FixtureGoogleSeam(json.loads((_FIXTURES / "google_ads_searchstream.json").read_text()))


async def test_run_backfill_not_backfillable_for_pagespeed(pg_session):
    _company, conn = await _seed_conn(pg_session, platform="pagespeed")
    progress = await backfill.run_connection_backfill(pg_session, conn, today=TODAY)
    assert progress.status == "not_backfillable" and progress.chunks == 0


async def test_run_backfill_advances_bounded_chunks(pg_session, monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_ADS_DEVELOPER_TOKEN", "dev-token")
    _company, conn = await _seed_conn(pg_session)

    # patch the injected seam in via run_connection_sync's http_client arg by
    # monkeypatching the dispatcher? simpler: the driver calls run_connection_sync
    # WITHOUT http_client, so patch the GoogleClient factory to our fixture seam.
    import src.marketing.ingest as ingest_pkg

    monkeypatch.setattr(ingest_pkg, "_google_seam", lambda connection, http_client: _google_seam())

    progress = await backfill.run_connection_backfill(pg_session, conn, today=TODAY, max_chunks=2)
    assert progress.chunks == 2
    assert progress.status == "more"  # more history remains beyond the 2-chunk budget
    facts = (
        await pg_session.execute(
            select(func.count()).select_from(AdsDailyMetric).where(AdsDailyMetric.connection_id == conn.id)
        )
    ).scalar_one()
    assert facts > 0  # backfill landed facts


class _EmptyGoogleSeam:
    """A successful searchStream that returns NO rows — a legitimately-empty
    historical window (pre-account-creation / paused / zero-spend period)."""

    async def post(self, url: str, json: dict[str, Any], *, headers: dict[str, str] | None = None) -> list[Any]:
        return []

    async def get(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:  # pragma: no cover
        return {}


async def test_run_backfill_advances_past_empty_windows(pg_session, monkeypatch):
    # Regression: a successful but EMPTY window writes 0 facts, so a fact-only
    # watermark would never move and the backfill would re-pull the same window
    # forever. The coverage watermark (successful backfill window_start) must
    # advance past empty windows.
    monkeypatch.setattr(settings, "GOOGLE_ADS_DEVELOPER_TOKEN", "dev-token")
    _company, conn = await _seed_conn(pg_session)
    import src.marketing.ingest as ingest_pkg

    monkeypatch.setattr(ingest_pkg, "_google_seam", lambda connection, http_client: _EmptyGoogleSeam())

    progress = await backfill.run_connection_backfill(pg_session, conn, today=TODAY, max_chunks=3)
    assert progress.chunks == 3  # advanced through 3 windows, not stuck on the first

    facts = (
        await pg_session.execute(
            select(func.count()).select_from(AdsDailyMetric).where(AdsDailyMetric.connection_id == conn.id)
        )
    ).scalar_one()
    assert facts == 0  # every window was empty

    starts = (
        await pg_session.execute(
            select(MarketingSyncRun.window_start)
            .where(MarketingSyncRun.connection_id == conn.id, MarketingSyncRun.run_type == "backfill")
            .order_by(MarketingSyncRun.window_start.desc())
        )
    ).scalars().all()
    assert len(starts) == 3 and len(set(starts)) == 3  # 3 DISTINCT, strictly-older windows


async def test_run_backfill_complete_at_floor(pg_session, monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_ADS_DEVELOPER_TOKEN", "dev-token")
    _company, conn = await _seed_conn(pg_session)
    floor = backfill.retention_floor(conn, today=TODAY)
    await _seed_ads_fact(pg_session, conn, floor)  # already at the floor → nothing to do
    progress = await backfill.run_connection_backfill(pg_session, conn, today=TODAY, max_chunks=3)
    assert progress.status == "complete" and progress.chunks == 0


async def test_run_backfill_skips_when_another_lane_holds_lock(pg_engine, pg_session):
    _company, conn = await _seed_conn(pg_session)

    # A second connection holds the per-connection advisory lock in an open txn —
    # the backfill driver must try_lock → False → skip ('locked'), not block.
    holder_maker = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with holder_maker() as holder, holder.begin():
        await warehouse.lock_connection(holder, conn.id)  # held for this txn
        progress = await backfill.run_connection_backfill(pg_session, conn, today=TODAY, max_chunks=2)

    assert progress.status == "locked" and progress.chunks == 0
