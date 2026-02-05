"""
Unit tests for the caching module.

Tests for in-memory caching utilities used for reference data.
"""

import pytest
from src.core.cache import (
    get_cache,
    cache_get,
    cache_set,
    cached_fetch,
    invalidate_cache,
    invalidate_all_caches,
    invalidate_tags_cache,
    invalidate_lead_sources_cache,
    invalidate_pipeline_stages_cache,
    CACHE_TAGS,
    CACHE_LEAD_SOURCES,
    CACHE_PIPELINE_STAGES,
)


class TestCacheBasics:
    """Tests for basic cache operations."""

    def test_get_cache_creates_new(self):
        """Test that get_cache creates a new cache if it doesn't exist."""
        cache = get_cache("test_new_cache")
        assert cache is not None

    def test_get_cache_returns_same(self):
        """Test that get_cache returns the same cache for the same name."""
        cache1 = get_cache("test_same_cache")
        cache2 = get_cache("test_same_cache")
        assert cache1 is cache2

    def test_cache_set_and_get(self):
        """Test setting and getting values from cache."""
        cache_name = "test_set_get"
        invalidate_cache(cache_name)  # Clear any existing

        cache_set(cache_name, "key1", "value1")
        result = cache_get(cache_name, "key1")
        assert result == "value1"

    def test_cache_get_missing_key(self):
        """Test getting a missing key returns None."""
        cache_name = "test_missing"
        invalidate_cache(cache_name)

        result = cache_get(cache_name, "nonexistent")
        assert result is None

    def test_invalidate_cache(self):
        """Test invalidating a specific cache."""
        cache_name = "test_invalidate"
        cache_set(cache_name, "key1", "value1")

        invalidate_cache(cache_name)
        result = cache_get(cache_name, "key1")
        assert result is None

    def test_invalidate_all_caches(self):
        """Test invalidating all caches."""
        cache_set("cache1", "key", "value1")
        cache_set("cache2", "key", "value2")

        invalidate_all_caches()

        assert cache_get("cache1", "key") is None
        assert cache_get("cache2", "key") is None


class TestCachedFetch:
    """Tests for the cached_fetch helper."""

    @pytest.mark.asyncio
    async def test_cached_fetch_cache_miss(self):
        """Test cached_fetch calls fetch_func on cache miss."""
        cache_name = "test_fetch_miss"
        invalidate_cache(cache_name)

        call_count = 0

        async def fetch_func():
            nonlocal call_count
            call_count += 1
            return ["item1", "item2"]

        result = await cached_fetch(cache_name, "key", fetch_func)
        assert result == ["item1", "item2"]
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_cached_fetch_cache_hit(self):
        """Test cached_fetch returns cached value on hit."""
        cache_name = "test_fetch_hit"
        invalidate_cache(cache_name)

        call_count = 0

        async def fetch_func():
            nonlocal call_count
            call_count += 1
            return ["item1", "item2"]

        # First call - cache miss
        result1 = await cached_fetch(cache_name, "key", fetch_func)
        # Second call - cache hit
        result2 = await cached_fetch(cache_name, "key", fetch_func)

        assert result1 == result2
        assert call_count == 1  # fetch_func called only once

    @pytest.mark.asyncio
    async def test_cached_fetch_different_keys(self):
        """Test cached_fetch with different keys."""
        cache_name = "test_fetch_keys"
        invalidate_cache(cache_name)

        async def fetch_func_1():
            return "data1"

        async def fetch_func_2():
            return "data2"

        result1 = await cached_fetch(cache_name, "key1", fetch_func_1)
        result2 = await cached_fetch(cache_name, "key2", fetch_func_2)

        assert result1 == "data1"
        assert result2 == "data2"


class TestConvenienceInvalidators:
    """Tests for convenience invalidation functions."""

    def test_invalidate_tags_cache(self):
        """Test invalidating tags cache."""
        cache_set(CACHE_TAGS, "test_key", "value")
        invalidate_tags_cache()
        assert cache_get(CACHE_TAGS, "test_key") is None

    def test_invalidate_lead_sources_cache(self):
        """Test invalidating lead sources cache."""
        cache_set(CACHE_LEAD_SOURCES, "test_key", "value")
        invalidate_lead_sources_cache()
        assert cache_get(CACHE_LEAD_SOURCES, "test_key") is None

    def test_invalidate_pipeline_stages_cache(self):
        """Test invalidating pipeline stages cache."""
        cache_set(CACHE_PIPELINE_STAGES, "test_key", "value")
        invalidate_pipeline_stages_cache()
        assert cache_get(CACHE_PIPELINE_STAGES, "test_key") is None


class TestCacheConstants:
    """Tests for cache name constants."""

    def test_cache_name_constants_are_unique(self):
        """Test that cache name constants are unique."""
        names = [CACHE_TAGS, CACHE_LEAD_SOURCES, CACHE_PIPELINE_STAGES]
        assert len(names) == len(set(names))

    def test_cache_name_constants_are_strings(self):
        """Test that cache name constants are strings."""
        assert isinstance(CACHE_TAGS, str)
        assert isinstance(CACHE_LEAD_SOURCES, str)
        assert isinstance(CACHE_PIPELINE_STAGES, str)
