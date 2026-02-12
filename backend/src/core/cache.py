"""In-memory caching utilities for shared reference data.

This module provides a comprehensive TTL-based in-memory cache with:
- Async-safe operations via asyncio.Lock
- Pattern-based key deletion
- Cache statistics and cleanup
- Decorator for caching async function results
- Entity-aware invalidation helpers

NOTE: This is for single-instance deployment only. For multi-instance
deployments, use Redis or another distributed cache.
"""

import asyncio
import sys
import time
import fnmatch
import functools
from typing import Any, Callable, TypeVar

# Legacy imports kept for backward compatibility with existing code
from cachetools import TTLCache as _CacheToolsTTL
import threading


# ---------------------------------------------------------------------------
# TTLCache - Async-safe in-memory cache
# ---------------------------------------------------------------------------

class TTLCache:
    """Simple in-memory TTL cache. Thread-safe via asyncio.Lock."""

    def __init__(self, default_ttl: int = 300):
        self._store: dict[str, tuple[Any, float]] = {}
        self._lock = asyncio.Lock()
        self._default_ttl = default_ttl
        self._hits = 0
        self._misses = 0

    async def get(self, key: str) -> Any | None:
        """Get value if exists and not expired."""
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self._misses += 1
                return None
            value, expires_at = entry
            if time.time() > expires_at:
                del self._store[key]
                self._misses += 1
                return None
            self._hits += 1
            return value

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Set value with TTL."""
        effective_ttl = ttl if ttl is not None else self._default_ttl
        async with self._lock:
            self._store[key] = (value, time.time() + effective_ttl)

    async def delete(self, key: str) -> None:
        """Delete specific key."""
        async with self._lock:
            self._store.pop(key, None)

    async def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching pattern (e.g., 'quotes:*'). Returns count deleted."""
        async with self._lock:
            keys_to_delete = [
                k for k in self._store if fnmatch.fnmatch(k, pattern)
            ]
            for k in keys_to_delete:
                del self._store[k]
            return len(keys_to_delete)

    async def clear(self) -> int:
        """Clear entire cache. Returns count cleared."""
        async with self._lock:
            count = len(self._store)
            self._store.clear()
            self._hits = 0
            self._misses = 0
            return count

    async def stats(self) -> dict:
        """Return cache stats: total keys, expired, memory estimate."""
        async with self._lock:
            now = time.time()
            total = len(self._store)
            expired = sum(1 for _, (_, exp) in self._store.items() if now > exp)
            active = total - expired
            memory_bytes = sum(
                sys.getsizeof(k) + sys.getsizeof(v)
                for k, (v, _) in self._store.items()
            )
            total_requests = self._hits + self._misses
            hit_rate = (self._hits / total_requests * 100) if total_requests > 0 else 0.0
            return {
                "total_keys": total,
                "active_keys": active,
                "expired_keys": expired,
                "memory_bytes": memory_bytes,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate_percent": round(hit_rate, 1),
            }

    async def cleanup(self) -> int:
        """Remove expired entries. Returns count removed."""
        async with self._lock:
            now = time.time()
            expired_keys = [k for k, (_, exp) in self._store.items() if now > exp]
            for k in expired_keys:
                del self._store[k]
            return len(expired_keys)


# Global cache instance
app_cache = TTLCache(default_ttl=300)


# ---------------------------------------------------------------------------
# Decorator for caching async function results
# ---------------------------------------------------------------------------

def cached(key_template: str, ttl: int = 300):
    """Decorator to cache async function results.

    Usage:
        @cached("pipeline_stages", ttl=600)
        async def get_pipeline_stages(db):
            ...

        @cached("tenant_settings:{tenant_id}", ttl=300)
        async def get_tenant_settings(db, tenant_id):
            ...
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Build cache key from template and kwargs/args
            try:
                # Try to format key from kwargs first, then positional args
                all_params = {}
                import inspect
                sig = inspect.signature(func)
                param_names = list(sig.parameters.keys())
                for i, arg in enumerate(args):
                    if i < len(param_names):
                        all_params[param_names[i]] = arg
                all_params.update(kwargs)
                cache_key = key_template.format(**all_params)
            except (KeyError, IndexError):
                cache_key = key_template

            # Check cache
            result = await app_cache.get(cache_key)
            if result is not None:
                return result

            # Call function and cache result
            result = await func(*args, **kwargs)
            if result is not None:
                await app_cache.set(cache_key, result, ttl=ttl)
            return result
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# Cache invalidation helpers
# ---------------------------------------------------------------------------

# Entity type to cache key pattern mapping
_ENTITY_CACHE_PATTERNS: dict[str, list[str]] = {
    "pipeline_stages": ["pipeline_stages*"],
    "lead_sources": ["lead_sources*"],
    "roles": ["roles*"],
    "tenant_settings": ["tenant_settings*"],
    "dashboard": ["dashboard*"],
    "admin_stats": ["admin_stats*", "team_overview*"],
}


async def invalidate_on_change(entity_type: str, entity_id: int | None = None) -> int:
    """Invalidate cache entries related to an entity change.

    Called after CRUD operations to keep cache fresh.
    Maps entity types to cache key patterns.
    Returns total count of deleted keys.
    """
    patterns = _ENTITY_CACHE_PATTERNS.get(entity_type, [])
    total_deleted = 0
    for pattern in patterns:
        total_deleted += await app_cache.delete_pattern(pattern)
    # Dashboard caches should also be invalidated on most entity changes
    if entity_type not in ("dashboard", "admin_stats"):
        total_deleted += await app_cache.delete_pattern("dashboard*")
        total_deleted += await app_cache.delete_pattern("admin_stats*")
        total_deleted += await app_cache.delete_pattern("team_overview*")
    return total_deleted


# ---------------------------------------------------------------------------
# Legacy API (backward compatibility with existing code using cachetools)
# ---------------------------------------------------------------------------

DEFAULT_TTL = 300
DEFAULT_MAXSIZE = 100

_cache_lock = threading.Lock()
_caches: dict[str, _CacheToolsTTL] = {}

CACHE_TAGS = "tags"
CACHE_LEAD_SOURCES = "lead_sources"
CACHE_PIPELINE_STAGES = "pipeline_stages"
CACHE_ROLES = "roles"
CACHE_TENANT_SETTINGS = "tenant_settings"
CACHE_DASHBOARD = "dashboard"
CACHE_ADMIN_STATS = "admin_stats"


def get_cache(name: str, maxsize: int = DEFAULT_MAXSIZE, ttl: int = DEFAULT_TTL) -> _CacheToolsTTL:
    """Get or create a named cache."""
    with _cache_lock:
        if name not in _caches:
            _caches[name] = _CacheToolsTTL(maxsize=maxsize, ttl=ttl)
        return _caches[name]


def invalidate_cache(name: str) -> None:
    """Invalidate (clear) a named cache."""
    with _cache_lock:
        if name in _caches:
            _caches[name].clear()


def invalidate_all_caches() -> None:
    """Invalidate all caches."""
    with _cache_lock:
        for cache in _caches.values():
            cache.clear()


T = TypeVar("T")


def cache_get(cache_name: str, key: str) -> Any | None:
    """Get a value from cache."""
    cache = get_cache(cache_name)
    with _cache_lock:
        return cache.get(key)


def cache_set(cache_name: str, key: str, value: Any) -> None:
    """Set a value in cache."""
    cache = get_cache(cache_name)
    with _cache_lock:
        cache[key] = value


async def cached_fetch(
    cache_name: str,
    key: str,
    fetch_func: Callable[[], Any],
) -> Any:
    """Fetch data with caching support.

    Checks cache first, if miss calls fetch_func and caches result.
    """
    cached_value = cache_get(cache_name, key)
    if cached_value is not None:
        return cached_value

    result = await fetch_func()
    cache_set(cache_name, key, result)
    return result


# Convenience functions for invalidating specific caches
def invalidate_tags_cache() -> None:
    """Invalidate the tags cache."""
    invalidate_cache(CACHE_TAGS)


def invalidate_lead_sources_cache() -> None:
    """Invalidate the lead sources cache."""
    invalidate_cache(CACHE_LEAD_SOURCES)


def invalidate_pipeline_stages_cache() -> None:
    """Invalidate the pipeline stages cache."""
    invalidate_cache(CACHE_PIPELINE_STAGES)


def invalidate_roles_cache() -> None:
    """Invalidate the roles cache."""
    invalidate_cache(CACHE_ROLES)


def invalidate_tenant_settings_cache() -> None:
    """Invalidate the tenant settings cache."""
    invalidate_cache(CACHE_TENANT_SETTINGS)


def invalidate_dashboard_cache() -> None:
    """Invalidate the dashboard cache."""
    invalidate_cache(CACHE_DASHBOARD)


def invalidate_admin_stats_cache() -> None:
    """Invalidate the admin stats cache."""
    invalidate_cache(CACHE_ADMIN_STATS)
