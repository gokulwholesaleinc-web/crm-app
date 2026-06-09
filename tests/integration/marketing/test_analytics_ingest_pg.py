"""End-to-end GA4 + GSC ingest on the real-PG tier (Phase 3).

Proves the multi-shape ``_sync_ga4`` / ``_sync_gsc`` flow: each issues three
requests (total + the two breakdown dimensions), the injected fixture seam routes
by the request body's ``dimensions`` (the C1 network boundary — no business logic
mocked), the pure mappers run for real, and the rows land at the right
``dimension_type`` so the read layer's GA4 top-pages + GSC queries/pages panels
populate. A second run restates (idempotent, A2) rather than duplicating.
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
from src.marketing import reads
from src.marketing.ingest import run_connection_sync
from src.marketing.models import AnalyticsDaily, PlatformConnection

pytestmark = pytest.mark.pg

_FIXTURES = Path(marketing_pkg.__file__).parent / "fixtures"
WINDOW_START = date(2026, 6, 1)
WINDOW_END = date(2026, 6, 2)


def _load(name: str) -> dict[str, Any]:
    return json.loads((_FIXTURES / name).read_text())


class _FixtureAnalyticsSeam:
    """Replays captured GA4/GSC payloads, routed by the request body's dimensions —
    exactly what the real runReport / searchAnalytics endpoints key on."""

    def __init__(self) -> None:
        self._f = {
            "ga4_total": _load("ga4_runreport_total.json"),
            "ga4_channels": _load("ga4_runreport_channels.json"),
            "ga4_pages": _load("ga4_runreport_pages.json"),
            "gsc_total": _load("gsc_searchanalytics.json"),
            "gsc_query": _load("gsc_searchanalytics_query.json"),
            "gsc_page": _load("gsc_searchanalytics_page.json"),
        }

    async def post(self, url: str, json: dict[str, Any], *, headers: dict[str, str] | None = None) -> dict[str, Any]:
        dims = json.get("dimensions", []) if isinstance(json, dict) else []
        names = [d["name"] if isinstance(d, dict) else d for d in dims]
        if "runReport" in url:  # GA4
            if "pagePath" in names:
                return self._f["ga4_pages"]
            if "sessionDefaultChannelGroup" in names:
                return self._f["ga4_channels"]
            return self._f["ga4_total"]
        # GSC searchAnalytics:query
        if "page" in names:
            return self._f["gsc_page"]
        if "query" in names:
            return self._f["gsc_query"]
        return self._f["gsc_total"]

    async def get(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:  # pragma: no cover
        return {}


async def _seed(session) -> tuple[Company, PlatformConnection, PlatformConnection]:
    company = Company(name="Analytics Co", status="customer")
    session.add(company)
    await session.flush()
    ga4_conn = PlatformConnection(
        company_id=company.id, platform="ga4", external_account_id="447532899",
        credential_mode="agency_oauth", currency="USD", status="pending",
    )
    gsc_conn = PlatformConnection(
        company_id=company.id, platform="gsc", external_account_id="sc-domain:example-client.com",
        credential_mode="agency_oauth", currency="USD", status="pending",
    )
    session.add_all([ga4_conn, gsc_conn])
    await session.flush()
    await session.commit()
    return company, ga4_conn, gsc_conn


async def _run_both(session, ga4_conn, gsc_conn) -> None:
    seam = _FixtureAnalyticsSeam()
    for conn in (ga4_conn, gsc_conn):
        run = await run_connection_sync(
            session, conn, run_type="daily",
            window_start=WINDOW_START, window_end=WINDOW_END, http_client=seam,
        )
        assert run.status == "success", run.error
    await session.commit()


async def test_ga4_gsc_ingest_lands_all_dimension_types(pg_session):
    _company, ga4_conn, gsc_conn = await _seed(pg_session)
    await _run_both(pg_session, ga4_conn, gsc_conn)

    async def _dims(conn_id: int, source: str) -> set[str]:
        rows = (
            await pg_session.execute(
                select(AnalyticsDaily.dimension_type)
                .where(AnalyticsDaily.connection_id == conn_id, AnalyticsDaily.source == source)
                .distinct()
            )
        ).scalars().all()
        return set(rows)

    assert await _dims(ga4_conn.id, "ga4") == {"total", "channel", "page"}
    assert await _dims(gsc_conn.id, "gsc") == {"total", "query", "page"}


async def test_read_layer_surfaces_top_pages_queries_and_gsc_pages(pg_session):
    company, ga4_conn, gsc_conn = await _seed(pg_session)
    await _run_both(pg_session, ga4_conn, gsc_conn)

    data = await reads.analytics(pg_session, company.id, WINDOW_START, WINDOW_END)

    assert data["ga4_configured"] is True
    assert data["gsc_configured"] is True
    # GA4 totals come ONLY from dimension_type='total' (A11) — not summed dim rows.
    assert data["ga4_totals"]["sessions"] > 0
    # GA4 top pages (page dim), ordered by sessions.
    assert {p["page"] for p in data["top_pages"]} == {"/", "/products"}
    # GSC queries + GSC pages both populated from their own dimension_type.
    assert {q["query"] for q in data["gsc_queries"]} == {"best widgets", "widget store near me"}
    assert {p["page"] for p in data["gsc_pages"]} == {
        "https://www.example-client.com/",
        "https://www.example-client.com/products",
    }
    # ratio-of-sums CTR on the home page across both days (60+55 clicks / 1500+1450 impr).
    home = next(p for p in data["gsc_pages"] if p["page"] == "https://www.example-client.com/")
    assert home["clicks"] == 115 and home["impressions"] == 2950


async def test_rerun_restates_not_duplicates(pg_session):
    _company, ga4_conn, gsc_conn = await _seed(pg_session)
    await _run_both(pg_session, ga4_conn, gsc_conn)
    after_first = (
        await pg_session.execute(select(func.count()).select_from(AnalyticsDaily))
    ).scalar_one()
    await _run_both(pg_session, ga4_conn, gsc_conn)
    after_second = (
        await pg_session.execute(select(func.count()).select_from(AnalyticsDaily))
    ).scalar_one()
    assert after_first == after_second  # restated on the natural grain (A2), not duplicated
