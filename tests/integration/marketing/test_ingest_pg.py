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
