"""stale_sync alert producer (B4 / CRITICAL-2) over the in-memory SQLite session.

The producer uses portable SELECT-then-write (no ON CONFLICT), so it runs on the
default test DB. Pins: a connection whose last successful sync is too old (or never)
opens exactly one deduplicated alert; a recovered connection auto-resolves it;
needs_reauth/disabled connections are not double-alarmed; re-runs don't duplicate.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.marketing import alerts
from src.marketing.models import MarketingAlert, PlatformConnection

_NOW = datetime(2026, 6, 9, 12, 0, tzinfo=UTC)


async def _conn(session: AsyncSession, company_id: int, **kw) -> PlatformConnection:
    defaults = dict(
        company_id=company_id, platform="google_ads", external_account_id="123",
        credential_mode="agency_oauth", status="active", is_enabled=True, failure_count=0,
    )
    defaults.update(kw)
    conn = PlatformConnection(**defaults)
    session.add(conn)
    await session.flush()
    return conn


async def _alerts(session: AsyncSession) -> list[MarketingAlert]:
    return list((await session.execute(select(MarketingAlert))).scalars().all())


class TestStaleSyncAlerts:
    async def test_never_synced_connection_opens_one_alert(self, db_session, test_company):
        conn = await _conn(db_session, test_company.id, last_synced_at=None)
        fired = await alerts.detect_stale_syncs(db_session, now=_NOW)
        assert fired == 1
        rows = await _alerts(db_session)
        assert len(rows) == 1
        a = rows[0]
        assert a.alert_type == "stale_sync"
        assert a.connection_id == conn.id
        assert a.is_resolved is False
        assert a.dedup_key == alerts.stale_sync_dedup_key(conn.id)
        assert a.severity == "warning"

    async def test_recently_synced_connection_no_alert(self, db_session, test_company):
        await _conn(db_session, test_company.id, last_synced_at=_NOW - timedelta(hours=2))
        assert await alerts.detect_stale_syncs(db_session, now=_NOW) == 0
        assert await _alerts(db_session) == []

    async def test_stale_then_recovered_auto_resolves(self, db_session, test_company):
        conn = await _conn(db_session, test_company.id, last_synced_at=_NOW - timedelta(hours=72))
        assert await alerts.detect_stale_syncs(db_session, now=_NOW) == 1
        # connection recovers (a later successful sync stamps freshness)
        conn.last_synced_at = _NOW
        await db_session.flush()
        assert await alerts.detect_stale_syncs(db_session, now=_NOW) == 0
        a = (await _alerts(db_session))[0]
        assert a.is_resolved is True

    async def test_rerun_is_deduplicated(self, db_session, test_company):
        await _conn(db_session, test_company.id, last_synced_at=None)
        await alerts.detect_stale_syncs(db_session, now=_NOW)
        await alerts.detect_stale_syncs(db_session, now=_NOW + timedelta(hours=1))
        rows = await _alerts(db_session)
        assert len(rows) == 1  # one open alert per connection; last_fired refreshed
        # SQLite returns naive datetimes (Postgres preserves tz) — compare tz-agnostic.
        assert rows[0].last_fired_at.replace(tzinfo=None) == (_NOW + timedelta(hours=1)).replace(tzinfo=None)

    async def test_needs_reauth_and_disabled_not_double_alarmed(self, db_session, test_company):
        # needs_reauth already surfaces via its own status; disabled is operator-silenced
        # (also excluded by the is_enabled filter). Neither should raise a stale_sync.
        await _conn(db_session, test_company.id, status="needs_reauth", last_synced_at=None)
        await _conn(
            db_session, test_company.id, platform="ga4", external_account_id="999",
            status="disabled", is_enabled=False, last_synced_at=None,
        )
        assert await alerts.detect_stale_syncs(db_session, now=_NOW) == 0
        assert await _alerts(db_session) == []
