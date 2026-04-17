"""Unit tests for core/permissions.py — PermissionChecker, factories, and guards."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.core.permissions import (
    PermissionChecker,
    check_record_access,
    get_user_role_name,
    require_admin,
    require_manager_or_above,
    require_permission,
)
from src.roles.models import RoleName


class TestPermissionChecker:
    """Tests for PermissionChecker.__call__."""

    async def test_superuser_always_allowed(self, test_superuser: User, db_session: AsyncSession):
        """Superuser bypasses RoleService and is returned unchanged."""
        checker = PermissionChecker("leads", "delete")
        result = await checker(test_superuser, db_session)
        assert result is test_superuser

    async def test_regular_user_with_permission(
        self, _sales_rep_user: User, db_session: AsyncSession, seed_roles: list
    ):
        """Sales rep with the required permission is returned unchanged."""
        checker = PermissionChecker("leads", "read")
        result = await checker(_sales_rep_user, db_session)
        assert result is _sales_rep_user

    async def test_regular_user_without_permission(
        self, _viewer_user: User, db_session: AsyncSession, seed_roles: list
    ):
        """User lacking permission gets HTTPException 403."""
        checker = PermissionChecker("leads", "delete")
        with pytest.raises(HTTPException) as exc_info:
            await checker(_viewer_user, db_session)
        assert exc_info.value.status_code == 403
        assert "delete" in exc_info.value.detail
        assert "leads" in exc_info.value.detail


class TestRequirePermissionFactory:
    """Tests for require_permission factory."""

    def test_returns_checker_with_correct_attributes(self):
        """require_permission returns a PermissionChecker with entity_type and action set."""
        checker = require_permission("leads", "create")
        assert isinstance(checker, PermissionChecker)
        assert checker.entity_type == "leads"
        assert checker.action == "create"

    def test_different_args_produce_independent_checkers(self):
        """Each call returns a distinct instance with its own attributes."""
        c1 = require_permission("contacts", "read")
        c2 = require_permission("leads", "delete")
        assert c1.entity_type == "contacts"
        assert c2.entity_type == "leads"
        assert c1 is not c2


class TestGetUserRoleName:
    """Tests for get_user_role_name."""

    async def test_superuser_returns_admin_without_db_query(
        self, test_superuser: User, db_session: AsyncSession
    ):
        """Superuser always returns 'admin' string."""
        result = await get_user_role_name(test_superuser, db_session)
        assert result == RoleName.ADMIN.value

    async def test_regular_user_delegates_to_role_service(
        self, _sales_rep_user: User, db_session: AsyncSession, seed_roles: list
    ):
        """Non-superuser gets their role name from RoleService."""
        result = await get_user_role_name(_sales_rep_user, db_session)
        assert result == RoleName.SALES_REP.value

    async def test_manager_user_returns_manager(
        self, _manager_user: User, db_session: AsyncSession, seed_roles: list
    ):
        """Manager user returns 'manager'."""
        result = await get_user_role_name(_manager_user, db_session)
        assert result == RoleName.MANAGER.value


class TestRequireAdmin:
    """Tests for require_admin dependency."""

    async def test_superuser_allowed(self, test_superuser: User, db_session: AsyncSession):
        """Superuser passes require_admin."""
        result = await require_admin(test_superuser, db_session)
        assert result is test_superuser

    async def test_admin_role_allowed(
        self, test_admin_user: User, db_session: AsyncSession, seed_roles: list
    ):
        """User with admin role passes require_admin (test_admin_user is superuser in conftest)."""
        result = await require_admin(test_admin_user, db_session)
        assert result is test_admin_user

    async def test_manager_role_denied(
        self, _manager_user: User, db_session: AsyncSession, seed_roles: list
    ):
        """Manager role raises 403."""
        with pytest.raises(HTTPException) as exc_info:
            await require_admin(_manager_user, db_session)
        assert exc_info.value.status_code == 403

    async def test_sales_rep_denied(
        self, _sales_rep_user: User, db_session: AsyncSession, seed_roles: list
    ):
        """Sales rep raises 403."""
        with pytest.raises(HTTPException) as exc_info:
            await require_admin(_sales_rep_user, db_session)
        assert exc_info.value.status_code == 403


class TestRequireManagerOrAbove:
    """Tests for require_manager_or_above dependency."""

    async def test_superuser_allowed(self, test_superuser: User, db_session: AsyncSession):
        """Superuser passes require_manager_or_above."""
        result = await require_manager_or_above(test_superuser, db_session)
        assert result is test_superuser

    async def test_admin_role_allowed(
        self, test_admin_user: User, db_session: AsyncSession, seed_roles: list
    ):
        """Admin role passes require_manager_or_above."""
        result = await require_manager_or_above(test_admin_user, db_session)
        assert result is test_admin_user

    async def test_manager_role_allowed(
        self, _manager_user: User, db_session: AsyncSession, seed_roles: list
    ):
        """Manager role passes require_manager_or_above."""
        result = await require_manager_or_above(_manager_user, db_session)
        assert result is _manager_user

    async def test_sales_rep_denied(
        self, _sales_rep_user: User, db_session: AsyncSession, seed_roles: list
    ):
        """Sales rep raises 403."""
        with pytest.raises(HTTPException) as exc_info:
            await require_manager_or_above(_sales_rep_user, db_session)
        assert exc_info.value.status_code == 403


class TestCheckRecordAccess:
    """Tests for check_record_access (synchronous)."""

    def _user(self, user_id: int):
        # check_record_access only reads .id; avoid SA model instantiation
        # (User.__new__ bypasses _sa_instance_state and User() has required fields).
        return SimpleNamespace(id=user_id)

    def test_admin_can_access_any_record(self):
        """Admin role never raises, regardless of owner_id."""
        entity = SimpleNamespace(owner_id=999)
        check_record_access(entity, self._user(1), RoleName.ADMIN.value)

    def test_manager_can_access_any_record(self):
        """Manager role never raises, regardless of owner_id."""
        entity = SimpleNamespace(owner_id=999)
        check_record_access(entity, self._user(1), RoleName.MANAGER.value)

    def test_sales_rep_owns_record(self):
        """Sales rep with matching owner_id does not raise."""
        entity = SimpleNamespace(owner_id=42)
        check_record_access(entity, self._user(42), RoleName.SALES_REP.value)

    def test_sales_rep_does_not_own_record(self):
        """Sales rep with mismatched owner_id raises 403."""
        entity = SimpleNamespace(owner_id=99)
        with pytest.raises(HTTPException) as exc_info:
            check_record_access(entity, self._user(42), RoleName.SALES_REP.value)
        assert exc_info.value.status_code == 403

    def test_entity_without_owner_id_attribute(self):
        """Entity with no owner_id attr does not raise for any role."""
        entity = SimpleNamespace()
        check_record_access(entity, self._user(1), RoleName.SALES_REP.value)

    def test_entity_with_owner_id_none(self):
        """Entity with owner_id=None does not raise — ownership not set."""
        entity = SimpleNamespace(owner_id=None)
        check_record_access(entity, self._user(1), RoleName.SALES_REP.value)
