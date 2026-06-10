"""End-to-end ingest on the real-PG tier — the glue the SQLite harness can't run.

The health machine + mappers are unit-tested; this proves the wiring in
``run_connection_sync`` works against real Postgres: advisory lock → credential
audit → fetch (injected fixture seam, the C1 network boundary) → land raw payload
→ pure map → ``ON CONFLICT`` upsert → sync-run row → health transition. A second
run re-upserts the same grains (idempotent restate, A2) rather than duplicating.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import src.marketing as marketing_pkg
from sqlalchemy import func, select
from src.companies.models import Company
from src.config import settings
from src.marketing.ingest import run_connection_sync
from src.marketing.models import (
    AdsDailyMetric,
    MarketingCampaign,
    MarketingCredentialAudit,
    MarketingRawPayload,
    PlatformConnection,
)

pytestmark = pytest.mark.pg

_FIXTURES = Path(marketing_pkg.__file__).parent / "fixtures"
WINDOW_START = date(2026, 6, 1)
WINDOW_END = date(2026, 6, 7)


class _FixtureGoogleSeam:
    """A GoogleSeam that replays a captured payload — no network, no business logic
    mocked (the mapper still runs for real over real captured JSON).

    The Google Ads fetcher now issues TWO searchStream POSTs (FROM campaign and FROM
    ad_group); route by the GAQL so each query gets its own captured batch list,
    exactly as the real searchStream endpoint would respond per query."""

    def __init__(self, payload: dict[str, Any]):
        self._payload = payload  # merged {"campaign_batches": [...], "adgroup_batches": [...]}

    async def post(self, url: str, json: dict[str, Any], *, headers: dict[str, str] | None = None) -> list[Any]:
        query = json.get("query", "") if isinstance(json, dict) else ""
        if "FROM ad_group" in query:
            return self._payload.get("adgroup_batches", [])
        return self._payload.get("campaign_batches", [])

    async def get(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._payload


async def _seed(session):
    company = Company(name="E2E Co", status="customer")
    session.add(company)
    await session.flush()
    conn = PlatformConnection(
        company_id=company.id,
        platform="google_ads",
        external_account_id="8328675647",
        credential_mode="mcc_link",
        currency="USD",
        status="pending",
        manager_account_id="8328675647",
    )
    session.add(conn)
    await session.flush()
    await session.commit()
    return company, conn


def _seam():
    payload = json.loads((_FIXTURES / "google_ads_searchstream.json").read_text())
    return _FixtureGoogleSeam(payload)


async def test_google_ads_ingest_lands_maps_upserts(pg_session, monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_ADS_DEVELOPER_TOKEN", "dev-token")
    _company, conn = await _seed(pg_session)

    run = await run_connection_sync(
        pg_session, conn, run_type="daily",
        window_start=WINDOW_START, window_end=WINDOW_END, http_client=_seam(),
    )
    await pg_session.commit()

    assert run.status == "success", run.error
    assert run.rows_upserted > 0

    # facts + dims landed
    fact_count = (
        await pg_session.execute(
            select(func.count()).select_from(AdsDailyMetric).where(AdsDailyMetric.connection_id == conn.id)
        )
    ).scalar_one()
    assert fact_count > 0
    spend = (
        await pg_session.execute(
            select(func.sum(AdsDailyMetric.spend)).where(AdsDailyMetric.connection_id == conn.id)
        )
    ).scalar_one()
    assert spend and spend > 0  # micros normalized to real dollars (A4)
    dims = (
        await pg_session.execute(
            select(func.count()).select_from(MarketingCampaign).where(MarketingCampaign.connection_id == conn.id)
        )
    ).scalar_one()
    assert dims > 0

    # raw payload landed (re-derivation hedge, A1)
    raw = (
        await pg_session.execute(
            select(func.count()).select_from(MarketingRawPayload).where(MarketingRawPayload.connection_id == conn.id)
        )
    ).scalar_one()
    assert raw == 1

    # credential access audited (B1) — and never the token
    audit = (
        await pg_session.execute(
            select(MarketingCredentialAudit).where(MarketingCredentialAudit.connection_id == conn.id)
        )
    ).scalars().all()
    assert any(a.action == "access" and a.actor_type == "ingest" for a in audit)

    # health transitioned to active with a real freshness stamp
    await pg_session.refresh(conn)
    assert conn.status == "active"
    assert conn.last_synced_at is not None
    assert conn.failure_count == 0


async def test_rerun_is_idempotent(pg_session, monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_ADS_DEVELOPER_TOKEN", "dev-token")
    _company, conn = await _seed(pg_session)

    await run_connection_sync(
        pg_session, conn, run_type="daily",
        window_start=WINDOW_START, window_end=WINDOW_END, http_client=_seam(),
    )
    await pg_session.commit()
    after_first = (
        await pg_session.execute(
            select(func.count()).select_from(AdsDailyMetric).where(AdsDailyMetric.connection_id == conn.id)
        )
    ).scalar_one()

    await run_connection_sync(
        pg_session, conn, run_type="daily",
        window_start=WINDOW_START, window_end=WINDOW_END, http_client=_seam(),
    )
    await pg_session.commit()
    after_second = (
        await pg_session.execute(
            select(func.count()).select_from(AdsDailyMetric).where(AdsDailyMetric.connection_id == conn.id)
        )
    ).scalar_one()

    assert after_first == after_second  # restated, not duplicated (A2)


class _DriftGoogleSeam:
    """A 2xx whose shape isn't a searchStream array/batch — proves run_connection_sync
    records 'partial' (not a silent zero) for a drifted production path (CRITICAL-1)."""

    async def post(self, url, json=None, *, headers=None):
        return {"error": {"code": 7, "message": "drifted"}}

    async def get(self, url, params=None):
        return {"error": {}}


async def test_drift_records_partial_and_keeps_freshness_honest(pg_session, monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_ADS_DEVELOPER_TOKEN", "dev-token")
    _company, conn = await _seed(pg_session)
    run = await run_connection_sync(
        pg_session, conn, run_type="daily",
        window_start=WINDOW_START, window_end=WINDOW_END, http_client=_DriftGoogleSeam(),
    )
    await pg_session.commit()
    assert run.status == "partial"  # NOT success, NOT a silent zero
    assert run.error_class == "unmappable_shape"
    await pg_session.refresh(conn)
    assert conn.last_synced_at is None  # a drifted run did not refresh → freshness honest
    assert conn.failure_count == 1


async def test_c1_account_includes_pmax_on_pg(pg_session, monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_ADS_DEVELOPER_TOKEN", "dev-token")
    _company, conn = await _seed(pg_session)
    await run_connection_sync(
        pg_session, conn, run_type="daily",
        window_start=WINDOW_START, window_end=WINDOW_END, http_client=_seam(),
    )
    await pg_session.commit()

    async def _level_spend(level):
        return (
            await pg_session.execute(
                select(func.coalesce(func.sum(AdsDailyMetric.spend), 0)).where(
                    AdsDailyMetric.connection_id == conn.id,
                    AdsDailyMetric.entity_level == level,
                )
            )
        ).scalar_one()

    from decimal import Decimal
    # account is summed from the PMax-inclusive campaign grain → exceeds the
    # ad-group-only sum (the C1 undercount the fix closes), on real Postgres.
    assert await _level_spend("account") == Decimal("25.750000")
    assert await _level_spend("adgroup") == Decimal("17.750000")


async def test_settling_restates_adgroup_grain(pg_session, monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_ADS_DEVELOPER_TOKEN", "dev-token")
    _company, conn = await _seed(pg_session)
    # settling must restate ALL grains (incl. ad-group) so late conversions don't
    # leave the ad-group drill-down undercounting vs the campaign totals.
    await run_connection_sync(
        pg_session, conn, run_type="settling",
        window_start=WINDOW_START, window_end=WINDOW_END, http_client=_seam(),
    )
    await pg_session.commit()
    adgroup_rows = (
        await pg_session.execute(
            select(func.count()).select_from(AdsDailyMetric).where(
                AdsDailyMetric.connection_id == conn.id,
                AdsDailyMetric.entity_level == "adgroup",
            )
        )
    ).scalar_one()
    assert adgroup_rows > 0
