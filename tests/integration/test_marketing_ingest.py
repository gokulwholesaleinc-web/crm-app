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

import httpx
import pytest
from src.marketing.ingest import IngestConfigError, _validate_public_url, health
from src.marketing.ingest.http_client import PermanentError, TransientError, _parse_retry_after
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
