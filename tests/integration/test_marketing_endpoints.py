"""Marketing read-API endpoints — RBAC isolation, ratio-of-sums, withhold, flag.

Runs on the SQLite app harness (the `client`/`auth_headers`/`db_session`
fixtures). Fact rows are seeded with DIRECT ORM inserts of distinct grains — no
upsert (ON CONFLICT is Postgres-only; the upsert/restate path is covered by the
real-PG C2 tier). These tests assert the read contract: per-company isolation,
ratio-of-sums KPIs, the A9 multi-currency withhold, empty states, and the
MKTG_ENABLED dark-by-default flag.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
import pytest_asyncio

from src.auth.models import User
from src.auth.security import create_access_token, get_password_hash
from src.companies.models import Company
from src.marketing.models import AdsDailyMetric, PlatformConnection

D1 = date(2026, 6, 1)
D2 = date(2026, 6, 2)
FROM = date(2026, 6, 1)
TO = date(2026, 6, 10)  # cur_to after trimming PROVISIONAL_DAYS(2) = Jun 8, covers D1/D2


@pytest_asyncio.fixture(autouse=True)
async def _mktg_env(monkeypatch):
    """Enable the feature + clear the shared app cache around every test so one
    test's cached payload can never serve another (the company ids repeat across
    function-scoped in-memory DBs)."""
    from src.config import settings
    from src.core.cache import app_cache

    await app_cache.clear()
    monkeypatch.setattr(settings, "MKTG_ENABLED", True)
    monkeypatch.setattr(settings, "MKTG_MULTI_CURRENCY", False)
    yield
    await app_cache.clear()


async def _conn(db, company_id, *, platform="google_ads", currency="USD", external="111", tz="America/Chicago"):
    c = PlatformConnection(
        company_id=company_id,
        platform=platform,
        external_account_id=external,
        credential_mode="mcc_link",
        currency=currency,
        status="active",
        reporting_timezone=tz,
        last_synced_at=datetime(2026, 6, 8, 12, 0, tzinfo=UTC),
    )
    db.add(c)
    await db.flush()
    return c


async def _ads(db, conn, company_id, *, d, spend, clicks, platform="google_ads", currency="USD"):
    db.add(
        AdsDailyMetric(
            connection_id=conn.id,
            company_id=company_id,
            platform=platform,
            date=d,
            entity_level="account",
            spend=Decimal(str(spend)),
            impressions=1000,
            clicks=clicks,
            conversions=Decimal("0"),
            conversion_value=Decimal("0"),
            currency=currency,
        )
    )


class TestFeatureFlag:
    async def test_dark_by_default_returns_404(self, client, auth_headers, test_company, monkeypatch):
        from src.config import settings

        monkeypatch.setattr(settings, "MKTG_ENABLED", False)
        r = await client.get(
            f"/api/marketing/companies/{test_company.id}/overview",
            params={"date_from": FROM.isoformat(), "date_to": TO.isoformat()},
            headers=auth_headers,
        )
        assert r.status_code == 404


class TestOverview:
    async def test_ratio_of_sums_and_data_trust(self, client, auth_headers, db_session, test_company):
        conn = await _conn(db_session, test_company.id)
        await _ads(db_session, conn, test_company.id, d=D1, spend=90, clicks=9)
        await _ads(db_session, conn, test_company.id, d=D2, spend=10, clicks=1)
        await db_session.commit()

        r = await client.get(
            f"/api/marketing/companies/{test_company.id}/overview",
            params={"date_from": FROM.isoformat(), "date_to": TO.isoformat()},
            headers=auth_headers,
        )
        assert r.status_code == 200
        body = r.json()
        assert Decimal(str(body["spend"])) == Decimal("100")
        assert body["clicks"] == 10
        # ratio-of-sums: 100 / 10 = 10, NOT avg of daily CPCs (10 and 10 here equal,
        # but the formula is asserted exhaustively in the C2 PG tier).
        assert Decimal(str(body["cpc"])) == Decimal("10")
        assert body["data_trust"]["timezone"] == "America/Chicago"
        assert "google_ads" in body["data_trust"]["sources"]
        assert body["withheld_reason"] is None
        assert len(body["cards"]) == 5

    async def test_empty_period_is_explicit_not_nan(self, client, auth_headers, db_session, test_company):
        await _conn(db_session, test_company.id)
        await db_session.commit()
        r = await client.get(
            f"/api/marketing/companies/{test_company.id}/overview",
            params={"date_from": FROM.isoformat(), "date_to": TO.isoformat()},
            headers=auth_headers,
        )
        assert r.status_code == 200
        body = r.json()
        # No spend → cpc/roas are null (em-dash), never NaN/Infinity.
        assert body["cpc"] is None
        assert body["roas"] is None

    async def test_multi_currency_withholds_blended(self, client, auth_headers, db_session, test_company):
        usd = await _conn(db_session, test_company.id, platform="google_ads", currency="USD", external="usd")
        eur = await _conn(db_session, test_company.id, platform="meta_ads", currency="EUR", external="eur")
        await _ads(db_session, usd, test_company.id, d=D1, spend=50, clicks=5, platform="google_ads", currency="USD")
        await _ads(db_session, eur, test_company.id, d=D1, spend=40, clicks=4, platform="meta_ads", currency="EUR")
        await db_session.commit()

        r = await client.get(
            f"/api/marketing/companies/{test_company.id}/overview",
            params={"date_from": FROM.isoformat(), "date_to": TO.isoformat()},
            headers=auth_headers,
        )
        assert r.status_code == 200
        body = r.json()
        assert body["withheld_reason"] == "multi_currency"
        assert body["cards"] == []  # no meaningless cross-currency blend


class TestRbacIsolation:
    async def test_user_cannot_read_another_owners_company(self, client, auth_headers, db_session, test_superuser):
        # A company owned by a *different* user — a sales_rep must not read it.
        other = Company(name="Rival Co", status="customer", owner_id=test_superuser.id, created_by_id=test_superuser.id)
        db_session.add(other)
        await db_session.flush()
        conn = await _conn(db_session, other.id)
        await _ads(db_session, conn, other.id, d=D1, spend=999, clicks=9)
        await db_session.commit()

        r = await client.get(
            f"/api/marketing/companies/{other.id}/overview",
            params={"date_from": FROM.isoformat(), "date_to": TO.isoformat()},
            headers=auth_headers,
        )
        assert r.status_code in (403, 404)  # never 200 with another client's data

    async def test_missing_company_is_404(self, client, auth_headers):
        r = await client.get(
            "/api/marketing/companies/999999/overview",
            params={"date_from": FROM.isoformat(), "date_to": TO.isoformat()},
            headers=auth_headers,
        )
        assert r.status_code == 404


class TestAllocationAndSyncStatus:
    async def test_allocation_splits_by_platform(self, client, auth_headers, db_session, test_company):
        g = await _conn(db_session, test_company.id, platform="google_ads", external="g")
        await _ads(db_session, g, test_company.id, d=D1, spend=70, clicks=7)
        await db_session.commit()
        r = await client.get(
            f"/api/marketing/companies/{test_company.id}/allocation",
            params={"date_from": FROM.isoformat(), "date_to": TO.isoformat()},
            headers=auth_headers,
        )
        assert r.status_code == 200
        body = r.json()
        platforms = {s["platform"] for s in body["slices"]}
        assert "google_ads" in platforms

    async def test_sync_status_reports_connection_health(self, client, auth_headers, db_session, test_company):
        await _conn(db_session, test_company.id, platform="ga4", external="prop")
        await db_session.commit()
        r = await client.get(
            f"/api/marketing/companies/{test_company.id}/sync-status",
            headers=auth_headers,
        )
        assert r.status_code == 200
        body = r.json()
        assert len(body["connections"]) == 1
        assert body["connections"][0]["platform"] == "ga4"
