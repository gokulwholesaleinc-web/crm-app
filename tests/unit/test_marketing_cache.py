"""D4 cache-key isolation — the cross-company leak guard.

The marketing cache must NEVER produce a company-agnostic key (the failure mode
of ``core.cache.cached`` that D4 forbids). These tests pin that two companies
never collide and that a missing/wrong-typed company_id raises rather than
silently sharing a key.
"""

import pytest

from src.marketing import cache


class TestMakeKey:
    def test_two_companies_never_collide(self):
        a = cache.make_key(company_id=1, endpoint="overview", date_from=None, date_to=None)
        b = cache.make_key(company_id=2, endpoint="overview", date_from=None, date_to=None)
        assert a != b
        assert a.startswith("mktg:1:")
        assert b.startswith("mktg:2:")

    def test_every_input_changes_the_key(self):
        from datetime import date

        base = dict(company_id=1, endpoint="series", date_from=date(2026, 6, 1), date_to=date(2026, 6, 7))
        k = cache.make_key(**base)
        assert cache.make_key(**{**base, "date_to": date(2026, 6, 8)}) != k
        assert cache.make_key(**{**base, "entity_level": "campaign"}) != k
        assert cache.make_key(**base, source="ga4") != k

    def test_none_compare_window_does_not_alias_a_date(self):
        from datetime import date

        with_none = cache.make_key(company_id=1, endpoint="o", compare_from=None)
        with_date = cache.make_key(company_id=1, endpoint="o", compare_from=date(2026, 1, 1))
        assert with_none != with_date

    def test_missing_company_id_raises(self):
        with pytest.raises(TypeError):
            cache.make_key(company_id=None, endpoint="overview")  # type: ignore[arg-type]

    def test_bool_company_id_rejected(self):
        # bool is an int subclass — must not pose as a company id.
        with pytest.raises(TypeError):
            cache.make_key(company_id=True, endpoint="overview")  # type: ignore[arg-type]

    def test_empty_endpoint_rejected(self):
        with pytest.raises(ValueError):
            cache.make_key(company_id=1, endpoint="")

    def test_colon_in_value_cannot_split_key(self):
        # an entity_level with a stray colon must not create extra segments
        k = cache.make_key(company_id=1, endpoint="o", entity_level="a:b")
        assert k.count(":") == cache.make_key(company_id=1, endpoint="o", entity_level="ab").count(":")


class TestGetOrComputeAndInvalidate:
    async def test_caches_then_serves_without_recompute(self):
        key = cache.make_key(company_id=4242, endpoint="overview")
        calls = {"n": 0}

        async def compute():
            calls["n"] += 1
            return {"spend": "1.00"}

        first = await cache.get_or_compute(key, compute, ttl=60)
        second = await cache.get_or_compute(key, compute, ttl=60)
        assert first == second == {"spend": "1.00"}
        assert calls["n"] == 1  # second call served from cache
        await cache.invalidate(4242)

    async def test_caches_empty_but_valid_result(self):
        key = cache.make_key(company_id=4243, endpoint="series")
        calls = {"n": 0}

        async def compute():
            calls["n"] += 1
            return []  # an empty period is a real answer, not a miss

        await cache.get_or_compute(key, compute, ttl=60)
        await cache.get_or_compute(key, compute, ttl=60)
        assert calls["n"] == 1
        await cache.invalidate(4243)

    async def test_invalidate_scoped_to_one_company(self):
        ka = cache.make_key(company_id=5001, endpoint="overview")
        kb = cache.make_key(company_id=5002, endpoint="overview")
        await cache.get_or_compute(ka, lambda: _const({"a": 1}), ttl=60)
        await cache.get_or_compute(kb, lambda: _const({"b": 2}), ttl=60)
        removed = await cache.invalidate(5001)
        assert removed >= 1
        # company 5002's cache survives 5001's invalidation
        served = {"n": 0}

        async def recompute():
            served["n"] += 1
            return {"b": 2}

        await cache.get_or_compute(kb, recompute, ttl=60)
        assert served["n"] == 0
        await cache.invalidate(5002)

    async def test_invalidate_rejects_bool(self):
        with pytest.raises(TypeError):
            await cache.invalidate(True)  # type: ignore[arg-type]


async def _const(value):
    return value
