"""Explicit-key marketing cache (D4) — never the ``@cached`` decorator.

PART III D4 forbids ``core.cache.cached`` for marketing reads: when an arg it
needs to interpolate is missing it falls back to the **bare key template** on a
``KeyError`` (see ``core/cache.py:cached``), so a key meant to be
``mktg:{company_id}:overview`` degrades to the literal ``mktg:overview`` shared
across every company → a cross-company data leak. This module instead builds the
key **explicitly** and **asserts** ``company_id`` is present + an ``int`` before
the key exists at all, so the unsafe path is unrepresentable.

Key shape (D4): ``mktg:{company_id}:{endpoint}:{date_from}:{date_to}:`` +
``{compare_from}:{compare_to}:{entity_level}[:{extra...}]`` — every input that
changes the result is in the key, and ``company_id`` is always first after the
namespace so ``delete_pattern("mktg:{company_id}:*")`` invalidates exactly one
client and nothing else.

TTL is deliberately > 5 min (D4: "raise TTL above 5 min") — marketing data
refreshes on a daily cron, so a stale read for a few minutes is cheaper than the
aggregation, and ingest calls ``invalidate(company_id)`` on write anyway.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import date
from typing import Any, TypeVar

from src.core.cache import app_cache

NAMESPACE = "mktg"
# > 5 min per D4; daily-cron data + invalidate-on-ingest make this safe.
DEFAULT_TTL = 900  # 15 minutes

T = TypeVar("T")


def _part(value: Any) -> str:
    """Render one key segment. ``None`` → ``"-"`` so ``compare_from=None`` and a
    literal date can never alias, and a stray ``:`` in a value can't split the key."""
    if value is None:
        return "-"
    if isinstance(value, date):
        return value.isoformat()
    return str(value).replace(":", "_")


def make_key(
    *,
    company_id: int,
    endpoint: str,
    date_from: date | None = None,
    date_to: date | None = None,
    compare_from: date | None = None,
    compare_to: date | None = None,
    entity_level: str | None = None,
    **extra: Any,
) -> str:
    """Build an explicit, company-scoped cache key.

    ``company_id`` MUST be a present, non-bool ``int`` — the D4 leak guard. A
    missing or wrong-typed ``company_id`` raises instead of silently producing a
    company-agnostic key that two clients would share.
    """
    # bool is an int subclass — reject it explicitly so True/False can't pose as a
    # company id and collapse two companies onto one key.
    if isinstance(company_id, bool) or not isinstance(company_id, int):
        raise TypeError(
            f"marketing cache key requires an int company_id, got {company_id!r}"
        )
    if not endpoint:
        raise ValueError("marketing cache key requires a non-empty endpoint")

    segments = [
        NAMESPACE,
        _part(company_id),
        _part(endpoint),
        _part(date_from),
        _part(date_to),
        _part(compare_from),
        _part(compare_to),
        _part(entity_level),
    ]
    # Deterministic ordering for any endpoint-specific extras (e.g. source, limit).
    for ekey in sorted(extra):
        segments.append(f"{ekey}={_part(extra[ekey])}")
    return ":".join(segments)


async def get_or_compute(
    key: str,
    compute: Callable[[], Awaitable[T]],
    *,
    ttl: int = DEFAULT_TTL,
) -> T:
    """Return the cached value for ``key`` or compute, cache, and return it.

    ``compute`` is a zero-arg coroutine factory (a ``lambda`` / ``partial``) so the
    expensive aggregation only runs on a miss. Unlike the ``@cached`` decorator
    this caches **any** non-``None`` result including empty-but-valid payloads
    (an empty period is a real answer, not a miss).
    """
    cached = await app_cache.get(key)
    if cached is not None:
        return cached
    value = await compute()
    if value is not None:
        await app_cache.set(key, value, ttl=ttl)
    return value


async def invalidate(company_id: int) -> int:
    """Drop every cached marketing read for one company (call on ingest write).

    Scoped to ``mktg:{company_id}:*`` so one client's refresh never evicts
    another's cache. Returns the number of keys removed.
    """
    if isinstance(company_id, bool) or not isinstance(company_id, int):
        raise TypeError(
            f"invalidate requires an int company_id, got {company_id!r}"
        )
    return await app_cache.delete_pattern(f"{NAMESPACE}:{company_id}:*")
