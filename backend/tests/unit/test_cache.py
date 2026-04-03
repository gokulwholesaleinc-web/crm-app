"""
Unit tests for the caching module.

Tests for in-memory caching utilities used for reference data.
Covers both the new async TTLCache and the legacy cachetools-based API.
"""

import asyncio
import time

import pytest
from src.core.cache import (
    # New TTLCache API
    TTLCache,
    app_cache,
    cached,
    invalidate_on_change,
    # Legacy API
    get_cache,
    cache_get,
    cache_set,
    cached_fetch,
    invalidate_cache,
    invalidate_all_caches,
    invalidate_tags_cache,
    invalidate_lead_sources_cache,
    invalidate_pipeline_stages_cache,
    invalidate_roles_cache,
    invalidate_tenant_settings_cache,
    invalidate_dashboard_cache,
    invalidate_admin_stats_cache,
    CACHE_TAGS,
    CACHE_LEAD_SOURCES,
    CACHE_PIPELINE_STAGES,
    CACHE_ROLES,
    CACHE_TENANT_SETTINGS,
    CACHE_DASHBOARD,
    CACHE_ADMIN_STATS,
)


# =========================================================================
# New TTLCache Tests
# =========================================================================


class TestTTLCache:
    """Tests for the new async TTLCache class."""

    @pytest.mark.asyncio
    async def test_get_set(self):
        """Test basic get/set operations."""
        cache = TTLCache(default_ttl=60)
        await cache.set("key1", "value1")
        result = await cache.get("key1")
        assert result == "value1"

    @pytest.mark.asyncio
    async def test_get_missing_key(self):
        """Test getting a missing key returns None."""
        cache = TTLCache(default_ttl=60)
        result = await cache.get("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_ttl_expiration(self):
        """Test that entries expire after TTL."""
        cache = TTLCache(default_ttl=1)
        await cache.set("key", "value", ttl=1)
        # Should be available immediately
        assert await cache.get("key") == "value"
        # Wait for expiration
        await asyncio.sleep(1.1)
        assert await cache.get("key") is None

    @pytest.mark.asyncio
    async def test_custom_ttl(self):
        """Test setting a custom TTL on individual entries."""
        cache = TTLCache(default_ttl=60)
        await cache.set("short", "value", ttl=1)
        await cache.set("long", "value", ttl=60)
        await asyncio.sleep(1.1)
        assert await cache.get("short") is None
        assert await cache.get("long") == "value"
        await cache.clear()

    @pytest.mark.asyncio
    async def test_delete(self):
        """Test deleting a specific key."""
        cache = TTLCache(default_ttl=60)
        await cache.set("key", "value")
        await cache.delete("key")
        assert await cache.get("key") is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self):
        """Test deleting a nonexistent key doesn't raise."""
        cache = TTLCache(default_ttl=60)
        await cache.delete("nonexistent")  # Should not raise

    @pytest.mark.asyncio
    async def test_delete_pattern(self):
        """Test deleting keys matching a pattern."""
        cache = TTLCache(default_ttl=60)
        await cache.set("dashboard:user1", "data1")
        await cache.set("dashboard:user2", "data2")
        await cache.set("settings:global", "data3")

        deleted = await cache.delete_pattern("dashboard:*")
        assert deleted == 2
        assert await cache.get("dashboard:user1") is None
        assert await cache.get("dashboard:user2") is None
        assert await cache.get("settings:global") == "data3"
        await cache.clear()

    @pytest.mark.asyncio
    async def test_delete_pattern_no_match(self):
        """Test delete_pattern returns 0 when no keys match."""
        cache = TTLCache(default_ttl=60)
        await cache.set("key1", "value1")
        deleted = await cache.delete_pattern("nonexistent:*")
        assert deleted == 0
        await cache.clear()

    @pytest.mark.asyncio
    async def test_clear(self):
        """Test clearing all entries."""
        cache = TTLCache(default_ttl=60)
        await cache.set("key1", "value1")
        await cache.set("key2", "value2")
        await cache.set("key3", "value3")

        count = await cache.clear()
        assert count == 3
        assert await cache.get("key1") is None
        assert await cache.get("key2") is None
        assert await cache.get("key3") is None

    @pytest.mark.asyncio
    async def test_clear_empty(self):
        """Test clearing an empty cache."""
        cache = TTLCache(default_ttl=60)
        count = await cache.clear()
        assert count == 0

    @pytest.mark.asyncio
    async def test_stats(self):
        """Test stats returns correct counts."""
        cache = TTLCache(default_ttl=60)
        await cache.clear()

        await cache.set("key1", "value1")
        await cache.set("key2", "value2")

        # Generate a hit and a miss
        await cache.get("key1")  # hit
        await cache.get("nonexistent")  # miss

        stats = await cache.stats()
        assert stats["total_keys"] == 2
        assert stats["active_keys"] == 2
        assert stats["expired_keys"] == 0
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate_percent"] == 50.0
        assert stats["memory_bytes"] > 0
        await cache.clear()

    @pytest.mark.asyncio
    async def test_stats_with_expired(self):
        """Test stats correctly counts expired entries."""
        cache = TTLCache(default_ttl=60)
        await cache.clear()

        await cache.set("expired", "value", ttl=1)
        await cache.set("active", "value", ttl=60)
        await asyncio.sleep(1.1)

        stats = await cache.stats()
        assert stats["total_keys"] == 2
        assert stats["expired_keys"] == 1
        assert stats["active_keys"] == 1
        await cache.clear()

    @pytest.mark.asyncio
    async def test_cleanup(self):
        """Test cleanup removes expired entries."""
        cache = TTLCache(default_ttl=60)
        await cache.set("expired1", "value", ttl=1)
        await cache.set("expired2", "value", ttl=1)
        await cache.set("active", "value", ttl=60)
        await asyncio.sleep(1.1)

        removed = await cache.cleanup()
        assert removed == 2
        assert await cache.get("active") == "value"
        await cache.clear()

    @pytest.mark.asyncio
    async def test_overwrite_value(self):
        """Test that setting a key twice overwrites the value."""
        cache = TTLCache(default_ttl=60)
        await cache.set("key", "old")
        await cache.set("key", "new")
        assert await cache.get("key") == "new"
        await cache.clear()

    @pytest.mark.asyncio
    async def test_complex_values(self):
        """Test caching complex objects like lists and dicts."""
        cache = TTLCache(default_ttl=60)
        data = [{"id": 1, "name": "test"}, {"id": 2, "name": "test2"}]
        await cache.set("complex", data)
        result = await cache.get("complex")
        assert result == data
        await cache.clear()


class TestCachedDecorator:
    """Tests for the @cached decorator."""

    @pytest.mark.asyncio
    async def test_cached_decorator_caches_result(self):
        """Test that the decorator caches function results."""
        await app_cache.clear()

        call_count = 0

        @cached("test_decorator_basic", ttl=60)
        async def expensive_func():
            nonlocal call_count
            call_count += 1
            return [1, 2, 3]

        result1 = await expensive_func()
        result2 = await expensive_func()

        assert result1 == [1, 2, 3]
        assert result2 == [1, 2, 3]
        assert call_count == 1  # Only called once
        await app_cache.clear()

    @pytest.mark.asyncio
    async def test_cached_decorator_with_params(self):
        """Test the decorator with parameterized key templates."""
        await app_cache.clear()

        call_count = 0

        @cached("test_param:{entity_id}", ttl=60)
        async def get_entity(entity_id: int):
            nonlocal call_count
            call_count += 1
            return {"id": entity_id, "name": f"Entity {entity_id}"}

        result1 = await get_entity(1)
        result2 = await get_entity(1)
        result3 = await get_entity(2)

        assert result1 == {"id": 1, "name": "Entity 1"}
        assert result2 == {"id": 1, "name": "Entity 1"}
        assert result3 == {"id": 2, "name": "Entity 2"}
        assert call_count == 2  # Called twice (once per unique entity_id)
        await app_cache.clear()

    @pytest.mark.asyncio
    async def test_cached_decorator_respects_ttl(self):
        """Test that the decorator respects TTL."""
        await app_cache.clear()

        call_count = 0

        @cached("test_ttl_decorator", ttl=1)
        async def short_lived():
            nonlocal call_count
            call_count += 1
            return "data"

        await short_lived()
        assert call_count == 1

        await asyncio.sleep(1.1)
        await short_lived()
        assert call_count == 2  # Re-fetched after TTL expired
        await app_cache.clear()

    @pytest.mark.asyncio
    async def test_cached_decorator_none_not_cached(self):
        """Test that None results are not cached."""
        await app_cache.clear()

        call_count = 0

        @cached("test_none_cache", ttl=60)
        async def returns_none():
            nonlocal call_count
            call_count += 1
            return None

        result1 = await returns_none()
        result2 = await returns_none()

        assert result1 is None
        assert result2 is None
        assert call_count == 2  # Called twice because None isn't cached
        await app_cache.clear()


class TestInvalidateOnChange:
    """Tests for the invalidate_on_change helper."""

    @pytest.mark.asyncio
    async def test_invalidate_pipeline_stages(self):
        """Test invalidating pipeline stages cache."""
        await app_cache.set("pipeline_stages:all", "data")
        deleted = await invalidate_on_change("pipeline_stages")
        assert deleted >= 1
        assert await app_cache.get("pipeline_stages:all") is None

    @pytest.mark.asyncio
    async def test_invalidate_lead_sources(self):
        """Test invalidating lead sources cache."""
        await app_cache.set("lead_sources:active", "data")
        deleted = await invalidate_on_change("lead_sources")
        assert deleted >= 1
        assert await app_cache.get("lead_sources:active") is None

    @pytest.mark.asyncio
    async def test_invalidate_also_clears_dashboard(self):
        """Test that non-dashboard entity changes also clear dashboard cache."""
        await app_cache.set("dashboard:user1", "data")
        await invalidate_on_change("pipeline_stages")
        assert await app_cache.get("dashboard:user1") is None

    @pytest.mark.asyncio
    async def test_invalidate_unknown_entity(self):
        """Test invalidating an unknown entity type doesn't fail."""
        await app_cache.set("dashboard:test", "data")
        deleted = await invalidate_on_change("unknown_entity")
        # Should still clear dashboard caches
        assert await app_cache.get("dashboard:test") is None
        await app_cache.clear()


# =========================================================================
# Legacy API Tests (backward compatibility)
# =========================================================================


class TestLegacyCacheBasics:
    """Tests for basic legacy cache operations."""

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
        invalidate_cache(cache_name)

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


class TestLegacyCachedFetch:
    """Tests for the legacy cached_fetch helper."""

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

        result1 = await cached_fetch(cache_name, "key", fetch_func)
        result2 = await cached_fetch(cache_name, "key", fetch_func)

        assert result1 == result2
        assert call_count == 1

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

    def test_invalidate_roles_cache(self):
        """Test invalidating roles cache."""
        cache_set(CACHE_ROLES, "test_key", "value")
        invalidate_roles_cache()
        assert cache_get(CACHE_ROLES, "test_key") is None

    def test_invalidate_tenant_settings_cache(self):
        """Test invalidating tenant settings cache."""
        cache_set(CACHE_TENANT_SETTINGS, "test_key", "value")
        invalidate_tenant_settings_cache()
        assert cache_get(CACHE_TENANT_SETTINGS, "test_key") is None

    def test_invalidate_dashboard_cache(self):
        """Test invalidating dashboard cache."""
        cache_set(CACHE_DASHBOARD, "test_key", "value")
        invalidate_dashboard_cache()
        assert cache_get(CACHE_DASHBOARD, "test_key") is None

    def test_invalidate_admin_stats_cache(self):
        """Test invalidating admin stats cache."""
        cache_set(CACHE_ADMIN_STATS, "test_key", "value")
        invalidate_admin_stats_cache()
        assert cache_get(CACHE_ADMIN_STATS, "test_key") is None


class TestCacheConstants:
    """Tests for cache name constants."""

    def test_cache_name_constants_are_unique(self):
        """Test that cache name constants are unique."""
        names = [
            CACHE_TAGS,
            CACHE_LEAD_SOURCES,
            CACHE_PIPELINE_STAGES,
            CACHE_ROLES,
            CACHE_TENANT_SETTINGS,
            CACHE_DASHBOARD,
            CACHE_ADMIN_STATS,
        ]
        assert len(names) == len(set(names))

    def test_cache_name_constants_are_strings(self):
        """Test that cache name constants are strings."""
        for name in [
            CACHE_TAGS,
            CACHE_LEAD_SOURCES,
            CACHE_PIPELINE_STAGES,
            CACHE_ROLES,
            CACHE_TENANT_SETTINGS,
            CACHE_DASHBOARD,
            CACHE_ADMIN_STATS,
        ]:
            assert isinstance(name, str)


