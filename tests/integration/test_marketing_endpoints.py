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

import pytest_asyncio
from src.companies.models import Company
from src.marketing.models import (
    AdsDailyMetric,
    AnalyticsDaily,
    BudgetPeriod,
    MarketingCampaign,
    PlatformConnection,
)

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


async def _ads(db, conn, company_id, *, d, spend, clicks, platform="google_ads", currency="USD",
               conversions=0, conversion_value=0, entity_level="account"):
    db.add(
        AdsDailyMetric(
            connection_id=conn.id,
            company_id=company_id,
            platform=platform,
            date=d,
            entity_level=entity_level,
            spend=Decimal(str(spend)),
            impressions=1000,
            clicks=clicks,
            conversions=Decimal(str(conversions)),
            conversion_value=Decimal(str(conversion_value)),
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


class TestCampaigns:
    async def test_campaign_table_populated_and_active_count_from_dim(
        self, client, auth_headers, db_session, test_company
    ):
        # H1 regression: campaign-level facts now exist, so the metrics table is
        # populated (it was structurally empty when only adgroup/account were written).
        conn = await _conn(db_session, test_company.id)
        db_session.add_all([
            MarketingCampaign(connection_id=conn.id, campaign_id="c1", name="Brand", status="enabled", raw_status="ENABLED"),
            MarketingCampaign(connection_id=conn.id, campaign_id="c2", name="Old", status="removed", raw_status="REMOVED"),
        ])
        for cid, spend, clicks in (("c1", 60, 6), ("c2", 40, 4)):
            db_session.add(AdsDailyMetric(
                connection_id=conn.id, company_id=test_company.id, platform="google_ads",
                date=D1, entity_level="campaign", campaign_id=cid, spend=Decimal(str(spend)),
                impressions=1000, clicks=clicks, conversions=Decimal("0"), conversion_value=Decimal("0"),
                currency="USD",
            ))
        await db_session.commit()

        r = await client.get(
            f"/api/marketing/companies/{test_company.id}/campaigns",
            params={"date_from": FROM.isoformat(), "date_to": TO.isoformat()},
            headers=auth_headers,
        )
        assert r.status_code == 200
        body = r.json()
        assert {c["name"] for c in body["campaigns"]} == {"Brand", "Old"}  # not empty
        # active_campaigns reads CURRENT dim status, not the facts → only the enabled one
        assert body["active_campaigns"] == 1
        c1 = next(c for c in body["campaigns"] if c["name"] == "Brand")
        assert Decimal(str(c1["cpc"])) == Decimal("10")  # ratio-of-sums 60/6


class TestAnalytics:
    async def test_ga4_totals_only_from_total_rows_and_key_events_surfaced(
        self, client, auth_headers, db_session, test_company
    ):
        conn = await _conn(db_session, test_company.id, platform="ga4", external="prop")
        # a 'total' row + a 'channel' row with DIFFERENT sessions — A11 says the total
        # must come ONLY from the 'total' row, never total+channel summed.
        db_session.add(AnalyticsDaily(
            connection_id=conn.id, company_id=test_company.id, source="ga4", date=D1,
            dimension_type="total", dimension_value="", sessions=1000, users=800,
            new_users=300, engaged_sessions=700, key_events=Decimal("37"),
        ))
        db_session.add(AnalyticsDaily(
            connection_id=conn.id, company_id=test_company.id, source="ga4", date=D1,
            dimension_type="channel", dimension_value="Organic Search", sessions=600, users=500,
        ))
        await db_session.commit()

        r = await client.get(
            f"/api/marketing/companies/{test_company.id}/analytics",
            params={"date_from": FROM.isoformat(), "date_to": TO.isoformat()},
            headers=auth_headers,
        )
        assert r.status_code == 200
        body = r.json()
        assert body["ga4_configured"] is True
        # A11: sessions total is ONLY the 'total' row (1000), not total+channel (1600)
        assert body["ga4_totals"]["sessions"] == 1000
        # H7: GA4's conversion metric is surfaced as key_events (no separate, duplicated
        # `conversions` field that could blend with ad-platform conversions).
        assert Decimal(str(body["ga4_totals"]["key_events"])) == Decimal("37")
        assert "conversions" not in body["ga4_totals"]
        assert body["ga4_totals"]["is_data_golden"] is True
        # traffic sources come from the channel rows, not the total
        assert "Organic Search" in {s["channel"] for s in body["traffic_sources"]}


class TestCrossPlatformConversionBlend:
    """BLEND: once >1 ad platform contributes, conversions/ROAS are non-additive and
    must be withheld; spend/clicks/impressions stay (additive within one currency)."""

    async def _seed_two_platforms(self, db, company_id):
        g = await _conn(db, company_id, platform="google_ads", external="g1", currency="USD")
        m = await _conn(db, company_id, platform="meta_ads", external="act_1", currency="USD")
        await _ads(db, g, company_id, d=D1, spend=100, clicks=50, conversions=10, conversion_value=500)
        await _ads(db, m, company_id, d=D1, spend=80, clicks=40, platform="meta_ads",
                   conversions=8, conversion_value=400)
        await db.commit()

    async def test_overview_withholds_conversions_keeps_spend(self, client, auth_headers, db_session, test_company):
        await self._seed_two_platforms(db_session, test_company.id)
        r = await client.get(
            f"/api/marketing/companies/{test_company.id}/overview",
            params={"date_from": FROM.isoformat(), "date_to": TO.isoformat()},
            headers=auth_headers,
        )
        assert r.status_code == 200
        body = r.json()
        assert body["conversions_withheld_reason"] == "multi_platform_conversions"
        # spend is additive across platforms within one currency → still blended (180)
        assert Decimal(str(body["spend"])) == Decimal("180")
        # conversion-derived blended numbers are withheld (None)
        assert body["conversions"] is None and body["roas"] is None
        card_keys = {c["key"] for c in body["cards"]}
        assert "spend" in card_keys and "conversions" not in card_keys and "roas" not in card_keys

    async def test_single_platform_still_shows_conversions(self, client, auth_headers, db_session, test_company):
        g = await _conn(db_session, test_company.id, platform="google_ads", external="g1")
        await _ads(db_session, g, test_company.id, d=D1, spend=100, clicks=50, conversions=10, conversion_value=500)
        await db_session.commit()
        r = await client.get(
            f"/api/marketing/companies/{test_company.id}/overview",
            params={"date_from": FROM.isoformat(), "date_to": TO.isoformat()},
            headers=auth_headers,
        )
        body = r.json()
        assert body["conversions_withheld_reason"] is None
        assert Decimal(str(body["conversions"])) == Decimal("10")

    async def test_series_withholds_conversions_per_point(self, client, auth_headers, db_session, test_company):
        await self._seed_two_platforms(db_session, test_company.id)
        r = await client.get(
            f"/api/marketing/companies/{test_company.id}/series",
            params={"date_from": FROM.isoformat(), "date_to": TO.isoformat()},
            headers=auth_headers,
        )
        body = r.json()
        assert body["conversions_withheld_reason"] == "multi_platform_conversions"
        pt = next(p for p in body["points"] if p["date"] == D1.isoformat())
        assert Decimal(str(pt["spend"])) == Decimal("180")  # additive
        assert pt["conversions"] is None and pt["roas"] is None


class TestMultiCurrencyWithholdOnTrends:
    """H2: /series and /day-of-week withhold for multi-currency, matching /overview."""

    async def _seed_two_currencies(self, db, company_id):
        g = await _conn(db, company_id, platform="google_ads", external="g1", currency="USD")
        m = await _conn(db, company_id, platform="meta_ads", external="act_1", currency="EUR")
        await _ads(db, g, company_id, d=D1, spend=100, clicks=50)
        await _ads(db, m, company_id, d=D1, spend=80, clicks=40, platform="meta_ads", currency="EUR")
        await db.commit()

    async def test_series_withheld_for_multi_currency(self, client, auth_headers, db_session, test_company):
        await self._seed_two_currencies(db_session, test_company.id)
        r = await client.get(
            f"/api/marketing/companies/{test_company.id}/series",
            params={"date_from": FROM.isoformat(), "date_to": TO.isoformat()},
            headers=auth_headers,
        )
        body = r.json()
        assert body["withheld_reason"] == "multi_currency"
        assert body["points"] == []

    async def test_day_of_week_withheld_for_multi_currency(self, client, auth_headers, db_session, test_company):
        await self._seed_two_currencies(db_session, test_company.id)
        r = await client.get(
            f"/api/marketing/companies/{test_company.id}/day-of-week",
            params={"date_from": FROM.isoformat(), "date_to": TO.isoformat()},
            headers=auth_headers,
        )
        body = r.json()
        assert body["withheld_reason"] == "multi_currency"
        assert body["days"] == []


class TestWindowAndParamValidation:
    async def test_bad_entity_level_is_422(self, client, auth_headers, test_company):
        r = await client.get(
            f"/api/marketing/companies/{test_company.id}/overview",
            params={"date_from": FROM.isoformat(), "date_to": TO.isoformat(), "entity_level": "garbage"},
            headers=auth_headers,
        )
        assert r.status_code == 422  # H6: not a silent all-zero answer

    async def test_inverted_range_is_422(self, client, auth_headers, test_company):
        r = await client.get(
            f"/api/marketing/companies/{test_company.id}/overview",
            params={"date_from": TO.isoformat(), "date_to": FROM.isoformat()},
            headers=auth_headers,
        )
        assert r.status_code == 422  # DATE-RANGE

    async def test_oversized_range_is_422(self, client, auth_headers, test_company):
        r = await client.get(
            f"/api/marketing/companies/{test_company.id}/overview",
            params={"date_from": "2020-01-01", "date_to": "2026-06-10"},
            headers=auth_headers,
        )
        assert r.status_code == 422  # DATE-RANGE cap

    async def test_one_sided_compare_is_422(self, client, auth_headers, db_session, test_company):
        await _conn(db_session, test_company.id)
        await db_session.commit()
        r = await client.get(
            f"/api/marketing/companies/{test_company.id}/overview",
            params={"date_from": FROM.isoformat(), "date_to": TO.isoformat(), "compare_from": "2026-05-01"},
            headers=auth_headers,
        )
        assert r.status_code == 422  # COMPARE-ASYM


class TestFreshnessNeverSynced:
    async def test_never_synced_active_connection_forces_never(self, client, auth_headers, db_session, test_company):
        # an active (non-pending) connection that has never synced must drag freshness
        # to "never" rather than be masked by a healthy sibling (FRESHNESS-MIN).
        good = await _conn(db_session, test_company.id, platform="google_ads", external="g1")
        stuck = await _conn(db_session, test_company.id, platform="meta_ads", external="act_1")
        stuck.last_synced_at = None  # active, enabled, never synced
        await _ads(db_session, good, test_company.id, d=D1, spend=10, clicks=5)
        await db_session.commit()
        r = await client.get(
            f"/api/marketing/companies/{test_company.id}/overview",
            params={"date_from": FROM.isoformat(), "date_to": TO.isoformat()},
            headers=auth_headers,
        )
        assert r.json()["data_trust"]["last_synced_at"] is None


class TestBudgetPacingNonFirstOfMonth:
    async def test_budget_row_stored_with_non_first_day_still_matches(self, client, auth_headers, db_session, test_company):
        conn = await _conn(db_session, test_company.id, platform="google_ads", external="g1")
        await _ads(db_session, conn, test_company.id, d=D1, spend=300, clicks=100)
        # budget row stored on the 15th, not the 1st (BUDGET-PERIODS range match)
        db_session.add(BudgetPeriod(
            connection_id=conn.id, company_id=test_company.id,
            period_month=date(2026, 6, 15), amount=Decimal("1000"), currency="USD",
        ))
        await db_session.commit()
        r = await client.get(
            f"/api/marketing/companies/{test_company.id}/budget-pacing",
            params={"as_of": "2026-06-10"},
            headers=auth_headers,
        )
        assert r.status_code == 200
        row = next(x for x in r.json()["rows"] if x["connection_id"] == conn.id)
        assert Decimal(str(row["budget"])) == Decimal("1000")  # matched despite day=15


class TestBlendDeltaAndDayOfWeek:
    """The two BLEND gaps the trio flagged: a multi-platform COMPARE window must not
    fabricate an overview delta against a blended baseline, and /day-of-week must
    withhold conversions when >1 ad platform contributes."""

    async def test_overview_delta_not_fabricated_against_blended_previous(
        self, client, auth_headers, db_session, test_company
    ):
        g = await _conn(db_session, test_company.id, platform="google_ads", external="g1")
        m = await _conn(db_session, test_company.id, platform="meta_ads", external="act_1")
        # CURRENT window: Google only (a valid single-platform conversions number)
        await _ads(db_session, g, test_company.id, d=D1, spend=100, clicks=50, conversions=10, conversion_value=500)
        # COMPARE window: Google + Meta both contributed (blended → non-additive)
        cmp_day = date(2026, 5, 22)
        await _ads(db_session, g, test_company.id, d=cmp_day, spend=90, clicks=40, conversions=5, conversion_value=250)
        await _ads(db_session, m, test_company.id, d=cmp_day, spend=70, clicks=30, platform="meta_ads",
                   conversions=4, conversion_value=200)
        await db_session.commit()

        r = await client.get(
            f"/api/marketing/companies/{test_company.id}/overview",
            params={
                "date_from": FROM.isoformat(), "date_to": TO.isoformat(),
                "compare_from": "2026-05-20", "compare_to": "2026-05-30",
            },
            headers=auth_headers,
        )
        assert r.status_code == 200
        body = r.json()
        # current is single-platform → not withheld; the value is the valid Google number
        assert body["conversions_withheld_reason"] is None
        assert Decimal(str(body["conversions"])) == Decimal("10")
        # but the conversions card delta must be "new" (baseline nulled), not a
        # fabricated % against the blended Google+Meta previous
        conv_card = next(c for c in body["cards"] if c["key"] == "conversions")
        assert conv_card["delta"]["is_new"] is True

    async def test_day_of_week_withholds_conversions_for_multi_platform(
        self, client, auth_headers, db_session, test_company
    ):
        g = await _conn(db_session, test_company.id, platform="google_ads", external="g1")
        m = await _conn(db_session, test_company.id, platform="meta_ads", external="act_1")
        await _ads(db_session, g, test_company.id, d=D1, spend=100, clicks=50, conversions=10, conversion_value=500)
        await _ads(db_session, m, test_company.id, d=D1, spend=80, clicks=40, platform="meta_ads",
                   conversions=8, conversion_value=400)
        await db_session.commit()

        r = await client.get(
            f"/api/marketing/companies/{test_company.id}/day-of-week",
            params={"date_from": FROM.isoformat(), "date_to": TO.isoformat()},
            headers=auth_headers,
        )
        assert r.status_code == 200
        body = r.json()
        assert body["conversions_withheld_reason"] == "multi_platform_conversions"
        day = next(d for d in body["days"] if Decimal(str(d["spend"])) > 0)
        assert Decimal(str(day["spend"])) == Decimal("180")  # additive
        assert day["conversions"] is None and day["roas"] is None and day["cost_per_conversion"] is None
