"""End-to-end Meta Ads ingest on the real-PG tier (mirrors test_ingest_pg.py).

Proves run_connection_sync wiring for meta_ads against real Postgres: flag gate →
advisory lock → credential audit → async-report fetch (injected fixture seam, the
C1 network boundary) → land raw → pure map → ON CONFLICT upsert → sync-run row →
health. The fixture seam replays the Graph async flow (submit → completed → insights
→ campaign/adset dims) from the committed landing fixture — no network, no mock.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
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


class _FixtureMetaSeam:
    """Replays the Meta Graph async-report flow from a captured landing fixture,
    routing by URL exactly as the real edges would respond — no network/mock."""

    def __init__(self, landing: dict[str, Any]):
        self._l = landing

    async def post(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        # submit → a report_run_id
        return {"report_run_id": "rr-test-1"}

    async def get(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if url.endswith("/insights"):
            return {"data": self._l["insights"], "paging": {}}
        if "/campaigns" in url:
            return {"data": self._l["campaigns"], "paging": {}}
        if "/adsets" in url:
            return {"data": self._l["adsets"], "paging": {}}
        # the report_run_id poll URL → completed immediately (no sleep)
        return {"async_status": "Job Completed", "async_percent_completion": 100}


def _seam() -> _FixtureMetaSeam:
    landing = json.loads((_FIXTURES / "meta_ads_insights.json").read_text())
    return _FixtureMetaSeam(landing)


async def _seed(session):
    company = Company(name="Meta E2E Co", status="customer")
    session.add(company)
    await session.flush()
    conn = PlatformConnection(
        company_id=company.id,
        platform="meta_ads",
        external_account_id="act_222",
        credential_mode="system_user",
        currency="USD",
        status="pending",
    )
    session.add(conn)
    await session.flush()
    await session.commit()
    return company, conn


async def test_meta_ingest_lands_maps_upserts(pg_session, monkeypatch):
    monkeypatch.setattr(settings, "MKTG_META_ENABLED", True)  # dark by default
    _company, conn = await _seed(pg_session)

    run = await run_connection_sync(
        pg_session, conn, run_type="daily",
        window_start=WINDOW_START, window_end=WINDOW_END, http_client=_seam(),
    )
    await pg_session.commit()

    assert run.status == "success", run.error
    assert run.rows_upserted > 0

    # account spend summed from ad sets, currency-decimal (not micros)
    spend = (
        await pg_session.execute(
            select(func.sum(AdsDailyMetric.spend)).where(
                AdsDailyMetric.connection_id == conn.id,
                AdsDailyMetric.entity_level == "account",
            )
        )
    ).scalar_one()
    assert spend == Decimal("23.500000")
    dims = (
        await pg_session.execute(
            select(func.count()).select_from(MarketingCampaign).where(MarketingCampaign.connection_id == conn.id)
        )
    ).scalar_one()
    assert dims == 2  # two campaigns
    raw = (
        await pg_session.execute(
            select(func.count()).select_from(MarketingRawPayload).where(MarketingRawPayload.connection_id == conn.id)
        )
    ).scalar_one()
    assert raw == 1
    audit = (
        await pg_session.execute(
            select(MarketingCredentialAudit).where(MarketingCredentialAudit.connection_id == conn.id)
        )
    ).scalars().all()
    assert any(a.action == "access" and a.actor_type == "ingest" for a in audit)

    await pg_session.refresh(conn)
    assert conn.status == "active" and conn.last_synced_at is not None and conn.failure_count == 0


async def test_meta_dark_when_flag_off(pg_session, monkeypatch):
    monkeypatch.setattr(settings, "MKTG_META_ENABLED", False)
    _company, conn = await _seed(pg_session)
    run = await run_connection_sync(
        pg_session, conn, run_type="daily",
        window_start=WINDOW_START, window_end=WINDOW_END, http_client=_seam(),
    )
    await pg_session.commit()
    assert run.status == "error"
    assert run.error_class == "flag_disabled"  # gated dark


async def test_meta_rerun_is_idempotent(pg_session, monkeypatch):
    monkeypatch.setattr(settings, "MKTG_META_ENABLED", True)
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
