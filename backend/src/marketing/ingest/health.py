"""Connection health state machine (B5) — explicit, pure transitions.

Classifies the outcome of a sync attempt and mutates a ``PlatformConnection``'s
``status`` / ``failure_count`` / ``last_synced_at`` / ``last_error`` accordingly.
Kept as small pure functions over the ORM row (no I/O) so the whole machine is
exercisable on SQLite (the integration tier just instantiates a row).

The locked rules (B5):

* **success** → ``failure_count = 0``, ``status = 'active'``, stamp ``last_synced_at``.
* **transient** (429 / RESOURCE_EXHAUSTED / 5xx / network) → ``failure_count += 1``,
  record the error, and leave ``status`` on ``active`` for the first
  ``TRANSIENT_ESCALATION_THRESHOLD - 1`` in a row (``failure_count`` drives
  backoff). Only *sustained* throttling escalates to ``error`` (CRITICAL-2) so a
  permanently-throttled connection can't read ``active`` forever.
* **reauth** (Google ``invalid_grant`` / Meta OAuth-190) → ``status = 'needs_reauth'``
  immediately, regardless of count.
* **hard failure** (any other permanent error) → ``failure_count += 1``; once it
  reaches ``HARD_FAILURE_THRESHOLD`` consecutive hard failures, ``status = 'error'``.
* ``disabled`` is operator-only and is never re-derived here.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum

from ..models import PlatformConnection
from .http_client import IngestHTTPError, PermanentError, TransientError

# N consecutive hard (non-transient, non-reauth) failures trip status='error' (B5).
HARD_FAILURE_THRESHOLD = 5

# CRITICAL-2: transient failures (429/RESOURCE_EXHAUSTED/5xx) deliberately do NOT
# flip an active connection on the first few — quota blips are normal. But a
# connection that is *permanently* throttled would otherwise climb failure_count
# forever while still reading 'active' (it never syncs, but never alarms). After
# this many CONSECUTIVE transient failures we escalate to 'error' so a
# stuck-throttled connection surfaces. Set well above HARD_FAILURE_THRESHOLD so
# transient stays the more forgiving class. At ~2 runs/day (daily + settling)
# this is ~5 days of unbroken throttling. Any success resets failure_count to 0.
TRANSIENT_ESCALATION_THRESHOLD = 10

# error_class tokens that mean "the credential is gone, reconnect needed".
_REAUTH_CLASSES = frozenset({"invalid_grant", "invalid_token", "oauth_exception_190"})


class Outcome(str, Enum):
    """The classified result of one sync attempt."""

    SUCCESS = "success"
    TRANSIENT = "transient"
    REAUTH = "reauth"
    HARD_FAILURE = "hard_failure"


def classify_exception(exc: BaseException) -> Outcome:
    """Map a raised exception to a health :class:`Outcome` (pure).

    Reauth is detected by ``error_class`` so it survives across the Google
    (``invalid_grant``) and Meta (``oauth_exception_190``) shapes alike.
    """
    if isinstance(exc, TransientError):
        return Outcome.TRANSIENT
    if isinstance(exc, PermanentError):
        if getattr(exc, "error_class", None) in _REAUTH_CLASSES:
            return Outcome.REAUTH
        return Outcome.HARD_FAILURE
    # Any non-HTTP exception (mapper bug, DB error mid-run) is a hard failure.
    return Outcome.HARD_FAILURE


def _error_class_of(exc: BaseException) -> str:
    return getattr(exc, "error_class", None) or type(exc).__name__


def apply_success(connection: PlatformConnection, *, now: datetime | None = None) -> None:
    """Record a successful sync (B5): reset failures, reactivate, stamp freshness."""
    connection.failure_count = 0
    connection.status = "active"
    connection.last_error = None
    connection.last_synced_at = now or datetime.now(UTC)


def apply_failure(connection: PlatformConnection, exc: BaseException) -> Outcome:
    """Transition a connection's health for a failed sync; return the outcome.

    Does NOT stamp ``last_synced_at`` — a failed run did not refresh the data, so
    freshness must stay truthful (the #1 vendor-dashboard sin we're fixing).
    """
    outcome = classify_exception(exc)
    connection.last_error = str(exc)[:1000]

    if outcome is Outcome.TRANSIENT:
        # Backoff signal — a few quota/5xx blips must never flip an active
        # connection. But sustained throttling (CRITICAL-2) eventually escalates so
        # a permanently-throttled connection stops reading 'active' forever.
        connection.failure_count = (connection.failure_count or 0) + 1
        if connection.failure_count >= TRANSIENT_ESCALATION_THRESHOLD:
            connection.status = "error"
        return outcome

    if outcome is Outcome.REAUTH:
        # Credential revoked: surface immediately, don't silently retry.
        connection.status = "needs_reauth"
        connection.failure_count = (connection.failure_count or 0) + 1
        return outcome

    # Hard failure: count up, trip 'error' only after N consecutive.
    connection.failure_count = (connection.failure_count or 0) + 1
    if connection.failure_count >= HARD_FAILURE_THRESHOLD:
        connection.status = "error"
    return outcome


def backoff_should_skip(connection: PlatformConnection) -> bool:
    """Cheap guard for the scheduler: a ``needs_reauth``/``disabled`` connection
    should be skipped (a fetch will just fail again) until an operator acts."""
    return connection.status in ("needs_reauth", "disabled")


def error_class_for_run(exc: BaseException) -> str:
    """The short token persisted to ``MarketingSyncRun.error_class``."""
    if isinstance(exc, IngestHTTPError):
        return _error_class_of(exc)
    return type(exc).__name__
