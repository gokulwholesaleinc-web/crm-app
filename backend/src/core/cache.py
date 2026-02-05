"""In-memory caching utilities for shared reference data.

This module provides lightweight caching for frequently accessed,
rarely-changing reference data like tags, lead sources, and pipeline stages.

NOTE: This is for single-instance deployment only. For multi-instance
deployments, use Redis or another distributed cache.
"""

from typing import Any, Callable, TypeVar
from cachetools import TTLCache
import threading

# Default TTL in seconds (5 minutes)
DEFAULT_TTL = 300

# Default max size for caches
DEFAULT_MAXSIZE = 100

# Thread-safe lock for cache operations
_cache_lock = threading.Lock()

# Named caches for different data types
_caches: dict[str, TTLCache] = {}


# Cache names as constants for consistency
CACHE_TAGS = "tags"
CACHE_LEAD_SOURCES = "lead_sources"
CACHE_PIPELINE_STAGES = "pipeline_stages"


def get_cache(name: str, maxsize: int = DEFAULT_MAXSIZE, ttl: int = DEFAULT_TTL) -> TTLCache:
    """Get or create a named cache.

    Args:
        name: Unique name for the cache
        maxsize: Maximum number of items in cache
        ttl: Time-to-live in seconds

    Returns:
        TTLCache instance
    """
    with _cache_lock:
        if name not in _caches:
            _caches[name] = TTLCache(maxsize=maxsize, ttl=ttl)
        return _caches[name]


def invalidate_cache(name: str) -> None:
    """Invalidate (clear) a named cache.

    Args:
        name: Name of the cache to invalidate
    """
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
    """Get a value from cache.

    Args:
        cache_name: Name of the cache
        key: Cache key

    Returns:
        Cached value or None if not found
    """
    cache = get_cache(cache_name)
    with _cache_lock:
        return cache.get(key)


def cache_set(cache_name: str, key: str, value: Any) -> None:
    """Set a value in cache.

    Args:
        cache_name: Name of the cache
        key: Cache key
        value: Value to cache
    """
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

    Args:
        cache_name: Name of the cache to use
        key: Cache key
        fetch_func: Async function to call on cache miss

    Returns:
        Cached or freshly fetched data

    Example:
        async def get_sources():
            return await cached_fetch(
                CACHE_LEAD_SOURCES,
                f"sources:{active_only}",
                lambda: service.get_all_sources(active_only),
            )
    """
    # Check cache first
    cached_value = cache_get(cache_name, key)
    if cached_value is not None:
        return cached_value

    # Fetch fresh data
    result = await fetch_func()

    # Cache the result
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
