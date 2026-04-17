"""Unit tests for core/cache.py — TTLCache, cached decorator, and invalidation helpers."""

import time

import pytest

from src.core.cache import TTLCache, cached, app_cache, invalidate_on_change


# ---------------------------------------------------------------------------
# TestTTLCache — basic get/set/delete behaviour
# ---------------------------------------------------------------------------

class TestTTLCache:
    @pytest.fixture(autouse=True)
    def fresh_cache(self):
        """Each test gets its own TTLCache instance."""
        self.cache = TTLCache(default_ttl=60)

    async def test_set_then_get_returns_value(self):
        await self.cache.set("key1", "hello")
        assert await self.cache.get("key1") == "hello"

    async def test_get_missing_key_returns_none(self):
        assert await self.cache.get("nonexistent") is None

    async def test_expired_entry_returns_none(self, monkeypatch):
        await self.cache.set("key1", "value", ttl=10)
        future = time.time() + 100
        monkeypatch.setattr(time, "time", lambda: future)
        assert await self.cache.get("key1") is None

    async def test_expired_entry_increments_misses(self, monkeypatch):
        await self.cache.set("key1", "value", ttl=10)
        real_time = time.time()
        monkeypatch.setattr(time, "time", lambda: real_time + 100)
        await self.cache.get("key1")
        stats = await self.cache.stats()
        assert stats["misses"] >= 1

    async def test_hits_counter_increments(self):
        await self.cache.set("key1", "value")
        await self.cache.get("key1")
        await self.cache.get("key1")
        stats = await self.cache.stats()
        assert stats["hits"] == 2

    async def test_misses_counter_increments(self):
        await self.cache.get("missing1")
        await self.cache.get("missing2")
        stats = await self.cache.stats()
        assert stats["misses"] == 2

    async def test_delete_removes_entry(self):
        await self.cache.set("key1", "value")
        await self.cache.delete("key1")
        assert await self.cache.get("key1") is None

    async def test_delete_pattern_removes_matching_keys(self):
        await self.cache.set("quotes:1", "a")
        await self.cache.set("quotes:2", "b")
        await self.cache.set("contacts:1", "c")
        count = await self.cache.delete_pattern("quotes:*")
        assert count == 2
        assert await self.cache.get("quotes:1") is None
        assert await self.cache.get("quotes:2") is None
        assert await self.cache.get("contacts:1") == "c"

    async def test_clear_empties_cache_and_returns_count(self):
        await self.cache.set("a", 1)
        await self.cache.set("b", 2)
        count = await self.cache.clear()
        assert count == 2
        assert await self.cache.get("a") is None

    async def test_default_ttl_respected(self, monkeypatch):
        cache = TTLCache(default_ttl=5)
        await cache.set("key1", "value")  # uses default_ttl=5
        real_time = time.time()
        monkeypatch.setattr(time, "time", lambda: real_time + 10)
        assert await cache.get("key1") is None

    async def test_per_call_ttl_overrides_default(self, monkeypatch):
        cache = TTLCache(default_ttl=5)
        await cache.set("key1", "value", ttl=200)  # long per-call TTL
        real_time = time.time()
        monkeypatch.setattr(time, "time", lambda: real_time + 10)
        assert await cache.get("key1") == "value"

    async def test_evict_expired_removes_only_past_ttl(self, monkeypatch):
        await self.cache.set("expires_soon", "x", ttl=5)
        await self.cache.set("lives_long", "y", ttl=300)
        real_time = time.time()
        monkeypatch.setattr(time, "time", lambda: real_time + 10)
        removed = await self.cache.cleanup()
        assert removed == 1
        # The long-lived key should survive (check by restoring time)
        monkeypatch.setattr(time, "time", lambda: real_time)
        assert await self.cache.get("lives_long") == "y"


# ---------------------------------------------------------------------------
# TestCachedDecorator — async caching decorator
# ---------------------------------------------------------------------------

class TestCachedDecorator:
    @pytest.fixture(autouse=True)
    async def reset_app_cache(self):
        """Clear app_cache before each test to avoid cross-test contamination."""
        await app_cache.clear()
        yield
        await app_cache.clear()

    async def test_caches_result_on_first_call_returns_cached_on_second(self):
        call_count = 0

        @cached("test_fn_result", ttl=60)
        async def fetch_data():
            nonlocal call_count
            call_count += 1
            return {"data": "value"}

        r1 = await fetch_data()
        r2 = await fetch_data()
        assert r1 == r2
        assert call_count == 1

    async def test_ttl_expiry_triggers_recomputation(self, monkeypatch):
        call_count = 0

        @cached("test_fn_expiry", ttl=5)
        async def fetch_data():
            nonlocal call_count
            call_count += 1
            return {"count": call_count}

        await fetch_data()
        real_time = time.time()
        monkeypatch.setattr(time, "time", lambda: real_time + 100)
        await fetch_data()
        assert call_count == 2

    async def test_different_args_produce_different_cache_entries(self):
        call_count = 0

        @cached("tenant_data:{tenant_id}", ttl=60)
        async def fetch_tenant(tenant_id: int):
            nonlocal call_count
            call_count += 1
            return {"tenant": tenant_id}

        r1 = await fetch_tenant(tenant_id=1)
        r2 = await fetch_tenant(tenant_id=2)
        r3 = await fetch_tenant(tenant_id=1)
        assert r1 == {"tenant": 1}
        assert r2 == {"tenant": 2}
        assert call_count == 2  # third call hits cache for tenant_id=1
        assert r3 == r1


# ---------------------------------------------------------------------------
# TestInvalidateOnChange — entity-aware invalidation
# ---------------------------------------------------------------------------

class TestInvalidateOnChange:
    @pytest.fixture(autouse=True)
    async def reset_app_cache(self):
        await app_cache.clear()
        yield
        await app_cache.clear()

    async def test_invalidation_clears_matching_entity_keys(self):
        await app_cache.set("pipeline_stages", {"stages": []})
        await app_cache.set("contacts:1", {"name": "Alice"})
        await invalidate_on_change("pipeline_stages")
        assert await app_cache.get("pipeline_stages") is None
        # contacts key is unrelated and should be unaffected
        assert await app_cache.get("contacts:1") == {"name": "Alice"}

    async def test_non_dashboard_entity_also_clears_dashboard(self):
        await app_cache.set("dashboard_overview", {"total": 5})
        await app_cache.set("pipeline_stages", {"stages": []})
        await invalidate_on_change("pipeline_stages")
        assert await app_cache.get("dashboard_overview") is None
