"""Conversion settling re-fetch (A7) — distinct from the spend lookback.

Ad platforms restate conversions for days after the click (Google up to the
account conversion window, default 30d / max 90d; Meta ~28d). The daily spend
lookback is short; settling is a SEPARATE, conversion-specific window that
re-fetches and re-upserts those trailing days so late conversions land.

This module only computes the settling window from a connection's
``conversion_window_days`` (clamped) — the actual re-fetch reuses the very same
``run_connection_sync`` machinery with ``run_type='settling'`` and these dates, so
there is no duplicated fetch/map/upsert path (DRY).
"""

from __future__ import annotations

from datetime import date, timedelta

from ..models import PlatformConnection

DEFAULT_CONVERSION_WINDOW_DAYS = 30
MAX_CONVERSION_WINDOW_DAYS = 90

# Only spend-bearing ad platforms have conversion settling; GA4/GSC/PageSpeed
# don't restate this way (GA4 attribution settling is handled by the lookback).
SETTLING_PLATFORMS = frozenset({"google_ads", "meta_ads", "instagram", "facebook", "tiktok", "linkedin"})


def conversion_window_days(connection: PlatformConnection) -> int:
    """The connection's settling window, clamped to ``[1, MAX]`` (A7)."""
    raw = connection.conversion_window_days or DEFAULT_CONVERSION_WINDOW_DAYS
    return max(1, min(int(raw), MAX_CONVERSION_WINDOW_DAYS))


def settling_window(connection: PlatformConnection, *, today: date) -> tuple[date, date]:
    """``(start, end)`` for the settling re-fetch — the trailing N days up to
    yesterday (``today`` excluded; today's data is incomplete)."""
    end = today - timedelta(days=1)
    start = end - timedelta(days=conversion_window_days(connection) - 1)
    return start, end


def needs_settling(connection: PlatformConnection) -> bool:
    """True iff this platform restates conversions and so warrants a settling run."""
    return connection.platform in SETTLING_PLATFORMS
