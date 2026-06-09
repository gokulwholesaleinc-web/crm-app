"""C2 — the warehouse gating acceptance test (Cluster-A definition of done).

Written before the warehouse existed; it is RED until ``marketing.warehouse`` +
``marketing.aggregation`` + ``marketing.money`` implement the locked behaviors,
GREEN after. Runs only on the real-Postgres tier (``MARKETING_TEST_PG_URL``)
because every assertion exercises something SQLite cannot:

* **Re-run a day → zero dups** — idempotent ``ON CONFLICT`` upsert (A2).
* **Late conversion → fact updates** — ``DO UPDATE`` restates, never ``DO NOTHING`` (A7).
* **Google micros vs Meta comparable** — money normalization makes 5,000,000 micros
  equal to ``"5.00"`` for the same dollar (A4 / NN-8).
* **Account-level NULL key restates, not duplicates** — ``NULLS NOT DISTINCT`` on the
  grain so a NULL campaign/adgroup row de-dups on re-run (A2).
* **Multi-currency → blended KPIs withheld** — single-currency-per-client default;
  a 2-currency client withholds blended KPIs until FX is scoped (A9 / Q11).

Plus the correctness rules these depend on: **ratio-of-sums not avg-of-ratios** (A5),
divide-by-zero → ``None`` (rendered "New"/em-dash), per-connection writer
serialization via an advisory lock (D2), and intra-batch dedupe.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from src.companies.models import Company
from src.marketing import aggregation, warehouse
from src.marketing.models import AdsDailyMetric, PlatformConnection
from src.marketing.money import from_micros, to_money
from src.marketing.rows import AdsDailyRow

pytestmark = pytest.mark.pg

D1 = date(2026, 6, 1)
D2 = date(2026, 6, 2)


async def _seed_connection(
    session,
    *,
    company_name: str,
    platform: str = "google_ads",
    currency: str = "USD",
    external: str = "1234567890",
) -> tuple[int, int]:
    """Create a Company + one active PlatformConnection; return (company_id, conn_id)."""
    company = Company(name=company_name, status="customer")
    session.add(company)
    await session.flush()
    conn = PlatformConnection(
        company_id=company.id,
        platform=platform,
        external_account_id=external,
        credential_mode="mcc_link",
        currency=currency,
        status="active",
    )
    session.add(conn)
    await session.flush()
    return company.id, conn.id


def _ads_row(conn_id, company_id, *, level, spend, conv=Decimal("0"), clicks=0,
             campaign_id=None, adgroup_id=None, currency="USD", d=D1, platform="google_ads"):
    return AdsDailyRow(
        connection_id=conn_id,
        company_id=company_id,
        platform=platform,
        date=d,
        entity_level=level,
        campaign_id=campaign_id,
        adgroup_id=adgroup_id,
        spend=spend,
        impressions=100,
        clicks=clicks,
        conversions=conv,
        conversion_value=Decimal("0"),
        currency=currency,
    )


async def _count(session, conn_id) -> int:
    res = await session.execute(
        select(func.count()).select_from(AdsDailyMetric).where(AdsDailyMetric.connection_id == conn_id)
    )
    return res.scalar_one()


@pytest_asyncio.fixture
async def seeded(pg_session):
    cid, conn = await _seed_connection(pg_session, company_name="Caputo's")
    await pg_session.commit()
    return pg_session, cid, conn


# ── A2: re-run a day is idempotent (zero dups) ──────────────────────────────
async def test_c2_rerun_day_yields_zero_dups(seeded):
    session, cid, conn = seeded
    batch = [
        _ads_row(conn, cid, level="account", spend=Decimal("50"), clicks=10),
        _ads_row(conn, cid, level="campaign", spend=Decimal("30"), clicks=6, campaign_id="c1"),
        _ads_row(conn, cid, level="campaign", spend=Decimal("20"), clicks=4, campaign_id="c2"),
    ]
    await warehouse.upsert_ads_daily(session, batch)
    await session.commit()
    await warehouse.upsert_ads_daily(session, batch)  # re-run the same day
    await session.commit()
    assert await _count(session, conn) == 3  # not 6


# ── A7: a late conversion restates the fact (DO UPDATE, never DO NOTHING) ────
async def test_c2_late_conversion_restates(seeded):
    session, cid, conn = seeded
    await warehouse.upsert_ads_daily(
        session, [_ads_row(conn, cid, level="account", spend=Decimal("50"), conv=Decimal("1"))]
    )
    await session.commit()
    # settling re-fetch surfaces a late conversion + a spend correction
    await warehouse.upsert_ads_daily(
        session, [_ads_row(conn, cid, level="account", spend=Decimal("52.5"), conv=Decimal("5"))]
    )
    await session.commit()
    row = (await session.execute(select(AdsDailyMetric).where(AdsDailyMetric.connection_id == conn))).scalar_one()
    assert row.conversions == Decimal("5")
    assert row.spend == Decimal("52.5")
    assert await _count(session, conn) == 1


# ── A4: Google micros and Meta dollars are comparable for the same amount ────
async def test_c2_google_micros_meta_comparable(pg_session):
    g_cid, g_conn = await _seed_connection(pg_session, company_name="MicrosCo", platform="google_ads", external="111")
    m_cid, m_conn = await _seed_connection(pg_session, company_name="MetaCo", platform="meta_ads", external="act_222")
    await pg_session.commit()

    google_spend = from_micros(5_000_000)  # ingest mapper normalizes micros ÷ 1e6
    meta_spend = to_money("5.00")
    await warehouse.upsert_ads_daily(pg_session, [
        _ads_row(g_conn, g_cid, level="account", spend=google_spend, platform="google_ads"),
        _ads_row(m_conn, m_cid, level="account", spend=meta_spend, platform="meta_ads"),
    ])
    await pg_session.commit()

    g = (await pg_session.execute(select(AdsDailyMetric.spend).where(AdsDailyMetric.connection_id == g_conn))).scalar_one()
    m = (await pg_session.execute(select(AdsDailyMetric.spend).where(AdsDailyMetric.connection_id == m_conn))).scalar_one()
    assert g == m == Decimal("5")


# ── A2: account-level NULL campaign/adgroup key restates, never duplicates ───
async def test_c2_account_null_key_restates_not_duplicates(seeded):
    session, cid, conn = seeded
    await warehouse.upsert_ads_daily(
        session, [_ads_row(conn, cid, level="account", spend=Decimal("5"), campaign_id=None, adgroup_id=None)]
    )
    await session.commit()
    await warehouse.upsert_ads_daily(
        session, [_ads_row(conn, cid, level="account", spend=Decimal("7.5"), campaign_id=None, adgroup_id=None)]
    )
    await session.commit()
    rows = (await session.execute(select(AdsDailyMetric).where(AdsDailyMetric.connection_id == conn))).scalars().all()
    assert len(rows) == 1  # NULLS NOT DISTINCT de-dups the NULL key
    assert rows[0].spend == Decimal("7.5")


# ── A9: a 2-currency client withholds blended KPIs; 1-currency does not ──────
async def test_c2_multi_currency_withholds_blended(pg_session):
    cid_usd, conn_usd = await _seed_connection(pg_session, company_name="DualFX", platform="google_ads", currency="USD", external="usd1")
    # second connection for the SAME company, different currency
    conn_eur = PlatformConnection(
        company_id=cid_usd, platform="meta_ads", external_account_id="act_eur",
        credential_mode="system_user", currency="EUR", status="active",
    )
    pg_session.add(conn_eur)
    await pg_session.flush()
    await warehouse.upsert_ads_daily(pg_session, [
        _ads_row(conn_usd, cid_usd, level="account", spend=Decimal("10"), currency="USD", platform="google_ads"),
        _ads_row(conn_eur.id, cid_usd, level="account", spend=Decimal("8"), currency="EUR", platform="meta_ads"),
    ])
    await pg_session.commit()

    currencies = await aggregation.distinct_currencies(pg_session, cid_usd)
    assert currencies == {"USD", "EUR"}
    assert aggregation.blended_withhold_reason(currencies, multi_currency_enabled=False) == "multi_currency"
    # opting into multi-currency lifts the withhold (FX applied at the reporting layer)
    assert aggregation.blended_withhold_reason(currencies, multi_currency_enabled=True) is None
    # a single-currency client is never withheld
    assert aggregation.blended_withhold_reason({"USD"}, multi_currency_enabled=False) is None


# ── A5: ratios are ratio-of-sums, not avg-of-daily-ratios; ÷0 → None ─────────
async def test_c2_overview_uses_ratio_of_sums(seeded):
    session, cid, conn = seeded
    # Day 1: $90 / 9 clicks (CPC 10). Day 2: $10 / 1 click (CPC 10) but choose
    # numbers where avg-of-ratios ≠ ratio-of-sums to prove the formula.
    await warehouse.upsert_ads_daily(session, [
        _ads_row(conn, cid, level="account", spend=Decimal("90"), clicks=9, d=D1),
        _ads_row(conn, cid, level="account", spend=Decimal("10"), clicks=1, d=D2),
    ])
    await session.commit()
    ov = await aggregation.ads_overview(session, cid, D1, D2, entity_level="account")
    # ratio-of-sums: 100 / 10 = 10.  avg-of-daily-ratios would be (10 + 10)/2 = 10 here,
    # so use a divide-by-zero check + an asymmetric case below to nail the formula.
    assert ov["spend"] == Decimal("100")
    assert ov["clicks"] == 10
    assert ov["cpc"] == Decimal("10")
    # conversions are zero → cost-per-conversion is None (rendered "New"/em-dash), not Infinity
    assert ov["cost_per_conversion"] is None


async def test_c2_overview_ratio_of_sums_is_not_avg_of_ratios(seeded):
    session, cid, conn = seeded
    # Day 1: $100 / 100 clicks → daily CPC 1.00. Day 2: $100 / 1 click → daily CPC 100.
    # avg-of-ratios = 50.50; ratio-of-sums = 200 / 101 ≈ 1.980198.
    await warehouse.upsert_ads_daily(session, [
        _ads_row(conn, cid, level="account", spend=Decimal("100"), clicks=100, d=D1),
        _ads_row(conn, cid, level="account", spend=Decimal("100"), clicks=1, d=D2),
    ])
    await session.commit()
    ov = await aggregation.ads_overview(session, cid, D1, D2, entity_level="account")
    assert ov["cpc"] == (Decimal("200") / Decimal("101")).quantize(Decimal("0.000001"))
    assert ov["cpc"] != Decimal("50.50")


# ── D2: a connection's writers serialize on an advisory lock ────────────────
async def test_c2_advisory_lock_serializes_writers(pg_engine, seeded):
    session, cid, conn = seeded
    from sqlalchemy.ext.asyncio import async_sessionmaker

    maker = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with maker() as holder:
        await holder.begin()
        await warehouse.lock_connection(holder, conn)  # blocking xact lock held until commit/rollback
        async with maker() as contender:
            got = await warehouse.try_lock_connection(contender, conn)
            assert got is False  # same connection_id is mutually excluded
            other = await warehouse.try_lock_connection(contender, conn + 999)
            assert other is True  # a different connection_id is independent
        await holder.rollback()  # releases the xact lock
    async with maker() as after:
        regained = await warehouse.try_lock_connection(after, conn)
        assert regained is True


# ── robustness: a grain appearing twice in one batch upserts once (last wins) ─
async def test_c2_intra_batch_dedup_last_wins(seeded):
    session, cid, conn = seeded
    await warehouse.upsert_ads_daily(session, [
        _ads_row(conn, cid, level="account", spend=Decimal("1")),
        _ads_row(conn, cid, level="account", spend=Decimal("9")),  # same grain, later in batch
    ])
    await session.commit()
    rows = (await session.execute(select(AdsDailyMetric).where(AdsDailyMetric.connection_id == conn))).scalars().all()
    assert len(rows) == 1
    assert rows[0].spend == Decimal("9")
