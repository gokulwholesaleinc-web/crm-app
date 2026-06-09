"""Health state-machine transitions (B5) — pure logic on a PlatformConnection row.

The health machine is pure over a ``PlatformConnection`` ORM instance (no I/O), so
it runs on the default in-memory SQLite harness with no Postgres. Pins every B5
rule: transient → backoff-no-disable, reauth → needs_reauth immediately, N hard →
error, success → reset + reactivate + stamp freshness.

The end-to-end ``run_connection_sync`` isolation (which touches the Postgres-only
``ON CONFLICT`` warehouse) lives in ``tests/integration/marketing/test_ingest_pg.py``
where the real-PG ``pg_session`` fixture is available.
"""

from __future__ import annotations

from datetime import date

import httpx
import pytest
from src.marketing.ingest import (
    IngestConfigError,
    _validate_public_url,
    ga4,
    google_ads,
    gsc,
    health,
    meta_ads,
)
from src.marketing.ingest.http_client import (
    PermanentError,
    TransientError,
    UnmappableShapeError,
    _parse_retry_after,
)
from src.marketing.models import PlatformConnection


def _conn(**kw) -> PlatformConnection:
    """A bare in-memory connection row (not persisted) for pure health tests."""
    defaults = dict(
        company_id=1, platform="ga4", external_account_id="447532899",
        credential_mode="agency_oauth", status="active", failure_count=0,
    )
    defaults.update(kw)
    return PlatformConnection(**defaults)


class TestHealthStateMachine:
    def test_transient_increments_count_but_keeps_active(self):
        conn = _conn(status="active", failure_count=2)
        outcome = health.apply_failure(conn, TransientError("429", error_class="transient_429"))
        assert outcome is health.Outcome.TRANSIENT
        assert conn.status == "active"  # quota never disables (B5)
        assert conn.failure_count == 3
        # a failed run must NOT stamp freshness
        assert conn.last_synced_at is None

    def test_resource_exhausted_is_transient(self):
        conn = _conn(status="active")
        outcome = health.apply_failure(conn, TransientError("RESOURCE_EXHAUSTED", error_class="transient_429"))
        assert outcome is health.Outcome.TRANSIENT
        assert conn.status == "active"

    def test_invalid_grant_sets_needs_reauth_immediately(self):
        conn = _conn(status="active", failure_count=0)
        outcome = health.apply_failure(conn, PermanentError("revoked", error_class="invalid_grant"))
        assert outcome is health.Outcome.REAUTH
        assert conn.status == "needs_reauth"  # immediate, regardless of count

    def test_meta_oauth_190_sets_needs_reauth(self):
        conn = _conn(status="active", platform="meta_ads")
        outcome = health.apply_failure(conn, PermanentError("190", error_class="oauth_exception_190"))
        assert outcome is health.Outcome.REAUTH
        assert conn.status == "needs_reauth"

    def test_sustained_transient_escalates_to_error(self):
        # CRITICAL-2: a few transient failures keep the connection active, but
        # sustained throttling eventually escalates so it can't read 'active' forever.
        conn = _conn(status="active", failure_count=health.TRANSIENT_ESCALATION_THRESHOLD - 2)
        health.apply_failure(conn, TransientError("429", error_class="transient_429"))
        assert conn.status == "active"  # one short of the escalation threshold
        assert conn.failure_count == health.TRANSIENT_ESCALATION_THRESHOLD - 1
        health.apply_failure(conn, TransientError("429", error_class="transient_429"))
        assert conn.status == "error"  # sustained throttling finally escalates
        assert conn.failure_count == health.TRANSIENT_ESCALATION_THRESHOLD
        # escalation threshold stays well above the hard-failure one (transient is
        # the more forgiving class).
        assert health.TRANSIENT_ESCALATION_THRESHOLD > health.HARD_FAILURE_THRESHOLD

    def test_success_after_transient_resets_below_escalation(self):
        # a recovery resets the counter so intermittent throttling never escalates.
        conn = _conn(status="active", failure_count=health.TRANSIENT_ESCALATION_THRESHOLD - 1)
        health.apply_success(conn)
        assert conn.failure_count == 0 and conn.status == "active"

    def test_n_consecutive_hard_failures_trip_error(self):
        conn = _conn(status="active", failure_count=health.HARD_FAILURE_THRESHOLD - 2)
        # one hard failure short of the threshold → still active
        health.apply_failure(conn, PermanentError("bad request", error_class="http_400"))
        assert conn.status == "active"
        assert conn.failure_count == health.HARD_FAILURE_THRESHOLD - 1
        # the Nth hard failure trips 'error'
        health.apply_failure(conn, PermanentError("bad request", error_class="http_400"))
        assert conn.status == "error"
        assert conn.failure_count == health.HARD_FAILURE_THRESHOLD

    def test_unexpected_exception_is_hard_failure(self):
        conn = _conn(status="active", failure_count=0)
        outcome = health.apply_failure(conn, ValueError("mapper bug"))
        assert outcome is health.Outcome.HARD_FAILURE
        assert conn.failure_count == 1

    def test_success_resets_and_reactivates(self):
        conn = _conn(status="error", failure_count=9)
        health.apply_success(conn)
        assert conn.status == "active"
        assert conn.failure_count == 0
        assert conn.last_error is None
        assert conn.last_synced_at is not None

    def test_backoff_should_skip_only_for_reauth_or_disabled(self):
        assert health.backoff_should_skip(_conn(status="needs_reauth")) is True
        assert health.backoff_should_skip(_conn(status="disabled")) is True
        assert health.backoff_should_skip(_conn(status="active")) is False
        assert health.backoff_should_skip(_conn(status="error")) is False

    def test_error_class_for_run(self):
        assert health.error_class_for_run(TransientError("x", error_class="transient_429")) == "transient_429"
        assert health.error_class_for_run(ValueError("boom")) == "ValueError"


class TestPageSpeedUrlGuard:
    """M-ssrf: the PageSpeed target URL is validated before it reaches the crawler."""

    def test_rejects_non_public_and_malformed(self):
        for bad in (
            "http://localhost/admin",
            "https://127.0.0.1/",
            "http://169.254.169.254/latest/meta-data/",  # cloud metadata
            "https://10.0.0.5/internal",
            "https://db.internal/",
            "ftp://example.com/",
            "not-a-url",
            "",
        ):
            with pytest.raises(IngestConfigError):
                _validate_public_url(bad)

    def test_allows_public_https(self):
        assert _validate_public_url("https://www.example-client.com/") == "https://www.example-client.com/"


class TestRetryAfterParsing:
    """LOW-retry-after: both the delta-seconds and the HTTP-date forms are honored."""

    def test_delta_seconds(self):
        resp = httpx.Response(429, headers={"Retry-After": "30"})
        assert _parse_retry_after(resp) == 30.0

    def test_http_date_form(self):
        # a far-future date → a positive (bounded) delay, no longer silently dropped
        resp = httpx.Response(429, headers={"Retry-After": "Wed, 21 Oct 2099 07:28:00 GMT"})
        val = _parse_retry_after(resp)
        assert val is not None and val > 0

    def test_missing_header(self):
        assert _parse_retry_after(httpx.Response(429)) is None


class TestSchedulerPlatformGate:
    """meta_ads is excluded from the daily selection until MKTG_META_ENABLED."""

    def test_meta_excluded_when_flag_off(self, monkeypatch):
        from src.config import settings
        from src.marketing.scheduler_hook import _allowed_platforms
        monkeypatch.setattr(settings, "MKTG_META_ENABLED", False)
        assert "meta_ads" not in _allowed_platforms()
        assert "google_ads" in _allowed_platforms()

    def test_meta_included_when_flag_on(self, monkeypatch):
        from src.config import settings
        from src.marketing.scheduler_hook import _allowed_platforms
        monkeypatch.setattr(settings, "MKTG_META_ENABLED", True)
        assert "meta_ads" in _allowed_platforms()


class _DriftSeam:
    """Returns one body for every call — proves a fetcher RAISES on an unrecognized
    2xx shape (drift) at the fetch boundary instead of normalizing it to a silent
    zero before the mapper guard can see it (CRITICAL-1, prod path)."""

    def __init__(self, body):
        self._b = body

    async def post(self, url, json=None, *, headers=None):
        return self._b

    async def get(self, url, params=None):
        return self._b


_W = dict(window_start=date(2026, 6, 1), window_end=date(2026, 6, 2))


class TestFetcherDriftGuard:
    async def test_google_ads_fetch_raises_on_drift(self):
        with pytest.raises(UnmappableShapeError):
            await google_ads.fetch_google_ads(
                _DriftSeam({"error": {"code": 7}}), customer_id="1", developer_token="t",
                login_customer_id=None, **_W,
            )

    async def test_google_ads_empty_array_is_genuine_empty(self):
        out = await google_ads.fetch_google_ads(
            _DriftSeam([]), customer_id="1", developer_token="t", login_customer_id=None, **_W
        )
        assert out == {"campaign_batches": [], "adgroup_batches": []}

    async def test_ga4_fetch_raises_on_drift(self):
        with pytest.raises(UnmappableShapeError):
            await ga4.fetch_ga4_total(_DriftSeam({"error": {}}), property_id="p", **_W)

    async def test_ga4_empty_report_is_genuine_empty(self):
        seam = _DriftSeam({"dimensionHeaders": [], "metricHeaders": [], "rows": []})
        out = await ga4.fetch_ga4_total(seam, property_id="p", **_W)
        assert out.get("rows") == []

    async def test_gsc_fetch_raises_on_drift(self):
        with pytest.raises(UnmappableShapeError):
            await gsc.fetch_gsc(_DriftSeam({"error": {}}), site_url="sc-domain:x.com", **_W)

    async def test_meta_paged_raises_on_drift(self):
        with pytest.raises(UnmappableShapeError):
            await meta_ads._fetch_paged(_DriftSeam({"error": {"code": 190}}), "https://x/insights", {})


class TestSsrfAlternateEncodings:
    def test_decimal_and_hex_loopback_blocked(self):
        for bad in ("http://2130706433/", "http://0x7f000001/"):
            with pytest.raises(IngestConfigError):
                _validate_public_url(bad)
