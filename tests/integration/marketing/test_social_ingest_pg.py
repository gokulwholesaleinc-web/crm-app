"""End-to-end organic-social ingest on the real-PG tier (Phase 4, dark).

Proves the IG + FB ingest path: fetch Graph insights (injected fixture seam, the
C1 network boundary) → land raw payload → pure map → upsert generic
``social_daily_metrics`` rows → the read layer surfaces per-platform metric
series + latest. Also pins the MKTG_SOCIAL_ENABLED dark-gate (a sync with the flag
off is recorded as a flag_disabled error, never a silent success) and idempotent
restate.
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
from src.marketing import reads
from src.marketing.ingest import run_connection_sync
from src.marketing.models import PlatformConnection, SocialDailyMetric

pytestmark = pytest.mark.pg

_FIXTURES = Path(marketing_pkg.__file__).parent / "fixtures"
WINDOW_START = date(2026, 6, 1)
WINDOW_END = date(2026, 6, 3)


def _load(name: str) -> dict[str, Any]:
    return json.loads((_FIXTURES / name).read_text())


class _FixtureSocialSeam:
    """A MetaSeam that replays one captured Graph insights payload (no network)."""

    def __init__(self, payload: dict[str, Any]):
        self._p = payload

    async def get(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._p

    async def post(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:  # pragma: no cover
        return {}


async def _seed(session) -> tuple[Company, PlatformConnection, PlatformConnection]:
    company = Company(name="Social Co", status="customer")
    session.add(company)
    await session.flush()
    ig = PlatformConnection(
        company_id=company.id, platform="instagram", external_account_id="17841400000000000",
        credential_mode="system_user", status="pending",
    )
    fb = PlatformConnection(
        company_id=company.id, platform="facebook", external_account_id="1234567890",
        credential_mode="system_user", status="pending",
    )
    session.add_all([ig, fb])
    await session.flush()
    await session.commit()
    return company, ig, fb


async def test_ig_fb_ingest_lands_and_reads(pg_session, monkeypatch):
    monkeypatch.setattr(settings, "MKTG_SOCIAL_ENABLED", True)
    company, ig, fb = await _seed(pg_session)

    ig_run = await run_connection_sync(
        pg_session, ig, run_type="daily", window_start=WINDOW_START, window_end=WINDOW_END,
        http_client=_FixtureSocialSeam(_load("instagram_insights.json")),
    )
    fb_run = await run_connection_sync(
        pg_session, fb, run_type="daily", window_start=WINDOW_START, window_end=WINDOW_END,
        http_client=_FixtureSocialSeam(_load("facebook_insights.json")),
    )
    await pg_session.commit()
    assert ig_run.status == "success", ig_run.error
    assert fb_run.status == "success", fb_run.error

    rows = (
        await pg_session.execute(select(func.count()).select_from(SocialDailyMetric))
    ).scalar_one()
    assert rows == 6 + 8  # IG 3 metrics×2d + FB 4 metrics×2d

    data = await reads.social(pg_session, company.id, WINDOW_START, WINDOW_END)
    assert {p["platform"] for p in data["platforms"]} == {"instagram", "facebook"}
    ig_p = next(p for p in data["platforms"] if p["platform"] == "instagram")
    follower = next(m for m in ig_p["metrics"] if m["metric_key"] == "follower_count")
    # latest = the most recent day's value (5412 on 2026-06-03)
    assert follower["latest"] == Decimal("5412.000000")
    assert [pt["date"] for pt in follower["series"]] == [date(2026, 6, 2), date(2026, 6, 3)]


async def test_rerun_restates_not_duplicates(pg_session, monkeypatch):
    monkeypatch.setattr(settings, "MKTG_SOCIAL_ENABLED", True)
    _company, ig, _fb = await _seed(pg_session)
    seam = _FixtureSocialSeam(_load("instagram_insights.json"))
    for _ in range(2):
        await run_connection_sync(
            pg_session, ig, run_type="daily", window_start=WINDOW_START, window_end=WINDOW_END,
            http_client=seam,
        )
        await pg_session.commit()
    rows = (
        await pg_session.execute(
            select(func.count()).select_from(SocialDailyMetric).where(SocialDailyMetric.connection_id == ig.id)
        )
    ).scalar_one()
    assert rows == 6  # restated on the (connection,date,platform,metric_key) grain, not duplicated


async def test_read_aggregates_across_same_platform_connections(pg_session):
    # A company can hold two IG accounts (the connection unique key is
    # (company, platform, external_account_id)). The read must return ONE
    # deterministic point per day (the total), not duplicate same-date points.
    company = Company(name="Two-IG Co", status="customer")
    pg_session.add(company)
    await pg_session.flush()
    ig_a = PlatformConnection(
        company_id=company.id, platform="instagram", external_account_id="111", credential_mode="system_user",
    )
    ig_b = PlatformConnection(
        company_id=company.id, platform="instagram", external_account_id="222", credential_mode="system_user",
    )
    pg_session.add_all([ig_a, ig_b])
    await pg_session.flush()
    for conn, base in ((ig_a, 1000), (ig_b, 50)):
        for d, delta in ((date(2026, 6, 2), 0), (date(2026, 6, 3), 5)):
            pg_session.add(
                SocialDailyMetric(
                    connection_id=conn.id, company_id=company.id, platform="instagram",
                    date=d, metric_key="follower_count", value=Decimal(base + delta),
                )
            )
    await pg_session.commit()

    data = await reads.social(pg_session, company.id, WINDOW_START, WINDOW_END)
    ig = next(p for p in data["platforms"] if p["platform"] == "instagram")
    fc = next(m for m in ig["metrics"] if m["metric_key"] == "follower_count")
    # one point per day (not four), each summed across the two accounts.
    assert [pt["date"] for pt in fc["series"]] == [date(2026, 6, 2), date(2026, 6, 3)]
    assert fc["series"][0]["value"] == Decimal("1050")  # 1000 + 50 (2026-06-02)
    assert fc["latest"] == Decimal("1060")  # (1000+5) + (50+5) (2026-06-03)


async def test_social_dark_when_flag_off(pg_session, monkeypatch):
    # The single ingest entry point keeps social dark even if a connection exists:
    # the run is a flag_disabled ERROR (truthful), never a silent success.
    monkeypatch.setattr(settings, "MKTG_SOCIAL_ENABLED", False)
    _company, ig, _fb = await _seed(pg_session)
    run = await run_connection_sync(
        pg_session, ig, run_type="daily", window_start=WINDOW_START, window_end=WINDOW_END,
        http_client=_FixtureSocialSeam(_load("instagram_insights.json")),
    )
    await pg_session.commit()
    assert run.status == "error"
    assert run.error_class == "flag_disabled"
    rows = (
        await pg_session.execute(select(func.count()).select_from(SocialDailyMetric))
    ).scalar_one()
    assert rows == 0  # nothing ingested while dark
