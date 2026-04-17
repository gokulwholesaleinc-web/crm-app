"""Shared helpers for dashboard sub-routers."""

import time
from datetime import date
from typing import Any


def _parse_date(date_str: str | None) -> date | None:
    """Parse a YYYY-MM-DD string to a date object."""
    if not date_str:
        return None
    return date.fromisoformat(date_str)


# Result-level cache for expensive dashboard queries (keyed by user_id).
# TTL is deliberately modest — dashboards are read-heavy and the data-scope /
# sharing layer does not currently invalidate this cache when role or share
# grants change, so stale data is bounded by the TTL below.
_dashboard_cache: dict[str, tuple[float, Any]] = {}
_DASHBOARD_CACHE_TTL = 180  # 3 minutes — long enough to let Neon auto-suspend


def _get_cached(key: str) -> Any | None:
    cached = _dashboard_cache.get(key)
    if cached and (time.monotonic() - cached[0]) < _DASHBOARD_CACHE_TTL:
        return cached[1]
    return None


def _set_cached(key: str, value: Any) -> None:
    _dashboard_cache[key] = (time.monotonic(), value)
