"""Unit tests for core/data_scope.py — DataScope dataclass, get_data_scope, cache, shared entities."""

import time

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.data_scope import (
    DataScope,
    _scope_cache,
    _SCOPE_CACHE_TTL,
    get_data_scope,
    invalidate_scope_cache,
)
from src.core.models import EntityShare


# ---------------------------------------------------------------------------
# TestDataScope — dataclass behaviour
# ---------------------------------------------------------------------------

class TestDataScope:
    def test_construction_with_all_fields(self):
        scope = DataScope(
            user_id=1,
            role_name="admin",
            owner_id=None,
            is_scoped=False,
            shared_entity_ids={"contacts": [10, 11]},
        )
        assert scope.user_id == 1
        assert scope.role_name == "admin"
        assert scope.owner_id is None
        assert scope.is_scoped is False
        assert scope.shared_entity_ids == {"contacts": [10, 11]}

    def test_scoped_true(self):
        scope = DataScope(user_id=42, role_name="sales_rep", owner_id=42, is_scoped=True)
        assert scope.is_scoped is True
        assert scope.owner_id == 42
        assert scope.can_see_all() is False
        assert scope.get_accessible_owner_ids() == [42]

    def test_unscoped(self):
        scope = DataScope(user_id=1, role_name="admin", owner_id=None, is_scoped=False)
        assert scope.can_see_all() is True
        assert scope.get_accessible_owner_ids() is None

    def test_get_shared_ids_returns_empty_when_missing(self):
        scope = DataScope(user_id=1, role_name="sales_rep", is_scoped=True)
        assert scope.get_shared_ids("leads") == []

    def test_get_shared_ids_returns_list(self):
        scope = DataScope(user_id=1, role_name="sales_rep", is_scoped=True,
                          shared_entity_ids={"leads": [5, 6]})
        assert scope.get_shared_ids("leads") == [5, 6]


# ---------------------------------------------------------------------------
# TestGetDataScope — role-based resolution via real SQLite session
# ---------------------------------------------------------------------------

class TestGetDataScope:
    async def test_admin_is_unscoped(
        self, db_session: AsyncSession, seed_roles, _manager_user
    ):
        # Use a non-superuser admin-role user — test_admin_user in conftest is actually
        # is_superuser=True, so use a dedicated admin-role non-superuser user
        from src.auth.models import User
        from src.auth.security import get_password_hash
        from src.roles.models import UserRole
        user = User(
            email="admin_nons@example.com",
            hashed_password=get_password_hash("pw"),
            full_name="Admin NS",
            is_active=True,
            is_superuser=False,
        )
        db_session.add(user)
        await db_session.flush()
        admin_role = next(r for r in seed_roles if r.name == "admin")
        db_session.add(UserRole(user_id=user.id, role_id=admin_role.id))
        await db_session.commit()
        await db_session.refresh(user)

        scope = await get_data_scope(user, db_session)
        assert scope.is_scoped is False
        assert scope.owner_id is None
        assert scope.role_name == "admin"

    async def test_manager_is_unscoped(
        self, db_session: AsyncSession, seed_roles, _manager_user
    ):
        scope = await get_data_scope(_manager_user, db_session)
        assert scope.is_scoped is False
        assert scope.owner_id is None
        assert scope.role_name == "manager"

    async def test_sales_rep_is_scoped(
        self, db_session: AsyncSession, seed_roles, _sales_rep_user
    ):
        scope = await get_data_scope(_sales_rep_user, db_session)
        assert scope.is_scoped is True
        assert scope.owner_id == _sales_rep_user.id

    async def test_viewer_is_scoped(
        self, db_session: AsyncSession, seed_roles, _viewer_user
    ):
        scope = await get_data_scope(_viewer_user, db_session)
        assert scope.is_scoped is True
        assert scope.owner_id == _viewer_user.id

    async def test_superuser_bypasses_role_check(
        self, db_session: AsyncSession, test_superuser
    ):
        scope = await get_data_scope(test_superuser, db_session)
        assert scope.is_scoped is False
        assert scope.owner_id is None
        assert scope.role_name == "admin"


# ---------------------------------------------------------------------------
# TestDataScopeCache — TTL and per-user isolation
# ---------------------------------------------------------------------------

class TestDataScopeCache:
    async def test_second_call_returns_cached(
        self, db_session: AsyncSession, seed_roles, _sales_rep_user
    ):
        """Two calls within TTL return the same DataScope object."""
        scope1 = await get_data_scope(_sales_rep_user, db_session)
        scope2 = await get_data_scope(_sales_rep_user, db_session)
        assert scope1 is scope2

    async def test_cache_expires_after_ttl(
        self, db_session: AsyncSession, seed_roles, _sales_rep_user
    ):
        """Manually back-date the cache entry so it appears expired; next call is fresh."""
        scope1 = await get_data_scope(_sales_rep_user, db_session)

        # Back-date the cached timestamp beyond the TTL
        cached_ts, cached_scope = _scope_cache[_sales_rep_user.id]
        _scope_cache[_sales_rep_user.id] = (cached_ts - _SCOPE_CACHE_TTL - 1, cached_scope)

        scope2 = await get_data_scope(_sales_rep_user, db_session)
        # Should be a fresh object (not the same instance)
        assert scope2 is not scope1

    async def test_different_users_have_separate_cache_entries(
        self, db_session: AsyncSession, seed_roles, _sales_rep_user, _viewer_user
    ):
        """Each user's scope is cached independently."""
        scope_sr = await get_data_scope(_sales_rep_user, db_session)
        scope_v = await get_data_scope(_viewer_user, db_session)
        assert scope_sr.user_id != scope_v.user_id
        assert _sales_rep_user.id in _scope_cache
        assert _viewer_user.id in _scope_cache

    def test_invalidate_single_user(self, _sales_rep_user):
        """invalidate_scope_cache(user_id) removes only that user's entry."""
        _scope_cache[_sales_rep_user.id] = (time.monotonic(), object())
        _scope_cache[999] = (time.monotonic(), object())
        invalidate_scope_cache(_sales_rep_user.id)
        assert _sales_rep_user.id not in _scope_cache
        assert 999 in _scope_cache
        _scope_cache.pop(999, None)

    def test_invalidate_all(self):
        """invalidate_scope_cache() with no args clears everything."""
        _scope_cache[1] = (time.monotonic(), object())
        _scope_cache[2] = (time.monotonic(), object())
        invalidate_scope_cache()
        assert len(_scope_cache) == 0


# ---------------------------------------------------------------------------
# TestSharedEntities — EntityShare integration
# ---------------------------------------------------------------------------

class TestSharedEntities:
    async def test_sales_rep_with_shared_entities(
        self, db_session: AsyncSession, seed_roles, _sales_rep_user
    ):
        """Shared EntityShare rows appear in scope.shared_entity_ids."""
        share = EntityShare(
            entity_type="contacts",
            entity_id=77,
            shared_with_user_id=_sales_rep_user.id,
            shared_by_user_id=_sales_rep_user.id,
        )
        db_session.add(share)
        await db_session.commit()

        scope = await get_data_scope(_sales_rep_user, db_session)
        assert 77 in scope.get_shared_ids("contacts")

    async def test_sales_rep_with_no_shares_has_empty_dict(
        self, db_session: AsyncSession, seed_roles, _sales_rep_user
    ):
        """No EntityShare rows → shared_entity_ids is empty."""
        scope = await get_data_scope(_sales_rep_user, db_session)
        assert scope.shared_entity_ids == {}
