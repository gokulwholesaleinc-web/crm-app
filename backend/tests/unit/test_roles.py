"""
Unit tests for RBAC roles endpoints.

Tests for listing roles, creating roles, updating permissions,
assigning roles to users, and permission enforcement (403 for unauthorized users).
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.auth.models import User
from src.auth.security import get_password_hash, create_access_token
from src.roles.models import Role, UserRole, RoleName, DEFAULT_PERMISSIONS


class TestListRoles:
    """Tests for listing roles."""

    @pytest.mark.asyncio
    async def test_list_roles_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        seed_roles: list[Role],
    ):
        """Test listing all roles."""
        response = await client.get(
            "/api/roles",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 4  # admin, manager, sales_rep, viewer
        role_names = [r["name"] for r in data]
        assert "admin" in role_names
        assert "manager" in role_names
        assert "sales_rep" in role_names
        assert "viewer" in role_names

    @pytest.mark.asyncio
    async def test_list_roles_includes_permissions(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        seed_roles: list[Role],
    ):
        """Test that role listing includes permissions."""
        response = await client.get(
            "/api/roles",
            headers=auth_headers,
        )

        data = response.json()
        admin_role = next(r for r in data if r["name"] == "admin")
        assert admin_role["permissions"] is not None
        assert "leads" in admin_role["permissions"]

    @pytest.mark.asyncio
    async def test_list_roles_unauthorized(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Test listing roles without auth returns 401."""
        response = await client.get("/api/roles")
        assert response.status_code == 401


class TestGetRole:
    """Tests for getting a role by ID."""

    @pytest.mark.asyncio
    async def test_get_role_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        seed_roles: list[Role],
    ):
        """Test getting a role by ID."""
        role = seed_roles[0]
        response = await client.get(
            f"/api/roles/{role.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == role.id
        assert data["name"] == role.name

    @pytest.mark.asyncio
    async def test_get_role_not_found(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test getting non-existent role returns 404."""
        response = await client.get(
            "/api/roles/99999",
            headers=auth_headers,
        )

        assert response.status_code == 404


class TestCreateRole:
    """Tests for creating new roles."""

    @pytest.mark.asyncio
    async def test_create_role_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict,
        seed_roles: list[Role],
    ):
        """Test creating a new custom role (admin only)."""
        response = await client.post(
            "/api/roles",
            headers=admin_auth_headers,
            json={
                "name": "custom_role",
                "description": "A custom role for testing",
                "permissions": {
                    "leads": ["read"],
                    "contacts": ["read", "create"],
                },
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "custom_role"
        assert data["description"] == "A custom role for testing"
        assert data["permissions"]["leads"] == ["read"]

    @pytest.mark.asyncio
    async def test_create_role_duplicate_name(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict,
        seed_roles: list[Role],
    ):
        """Test creating role with existing name returns 409."""
        response = await client.post(
            "/api/roles",
            headers=admin_auth_headers,
            json={
                "name": "admin",  # Already exists
                "description": "Duplicate",
                "permissions": {},
            },
        )

        assert response.status_code == 409
        assert "already exists" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_create_role_non_admin_forbidden(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        viewer_auth_headers: dict,
        seed_roles: list[Role],
    ):
        """Test that non-admin users cannot create roles (403)."""
        response = await client.post(
            "/api/roles",
            headers=viewer_auth_headers,
            json={
                "name": "forbidden_role",
                "description": "Should not be created",
                "permissions": {},
            },
        )

        assert response.status_code == 403


class TestUpdateRole:
    """Tests for updating role permissions."""

    @pytest.mark.asyncio
    async def test_update_role_permissions(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict,
        seed_roles: list[Role],
    ):
        """Test updating role permissions."""
        # Create a custom role to update
        create_response = await client.post(
            "/api/roles",
            headers=admin_auth_headers,
            json={
                "name": "updatable_role",
                "description": "Original description",
                "permissions": {"leads": ["read"]},
            },
        )
        role_id = create_response.json()["id"]

        response = await client.patch(
            f"/api/roles/{role_id}",
            headers=admin_auth_headers,
            json={
                "description": "Updated description",
                "permissions": {"leads": ["read", "create", "update"]},
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["description"] == "Updated description"
        assert "create" in data["permissions"]["leads"]
        assert "update" in data["permissions"]["leads"]

    @pytest.mark.asyncio
    async def test_update_role_non_admin_forbidden(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        viewer_auth_headers: dict,
        seed_roles: list[Role],
    ):
        """Test that non-admin users cannot update roles (403)."""
        role = seed_roles[0]
        response = await client.patch(
            f"/api/roles/{role.id}",
            headers=viewer_auth_headers,
            json={"description": "Should not update"},
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_update_role_not_found(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict,
        seed_roles: list[Role],
    ):
        """Test updating non-existent role returns 404."""
        response = await client.patch(
            "/api/roles/99999",
            headers=admin_auth_headers,
            json={"description": "Test"},
        )

        assert response.status_code == 404


class TestDeleteRole:
    """Tests for deleting roles."""

    @pytest.mark.asyncio
    async def test_delete_custom_role(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict,
        seed_roles: list[Role],
    ):
        """Test deleting a custom (non-default) role."""
        # Create custom role
        create_response = await client.post(
            "/api/roles",
            headers=admin_auth_headers,
            json={
                "name": "deletable_role",
                "description": "To be deleted",
                "permissions": {},
            },
        )
        role_id = create_response.json()["id"]

        response = await client.delete(
            f"/api/roles/{role_id}",
            headers=admin_auth_headers,
        )

        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_default_role_fails(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict,
        seed_roles: list[Role],
    ):
        """Test that default roles cannot be deleted (400)."""
        admin_role = next(r for r in seed_roles if r.name == "admin")

        response = await client.delete(
            f"/api/roles/{admin_role.id}",
            headers=admin_auth_headers,
        )

        assert response.status_code == 400
        assert "cannot delete default role" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_delete_role_non_admin_forbidden(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        viewer_auth_headers: dict,
        seed_roles: list[Role],
    ):
        """Test that non-admin users cannot delete roles (403)."""
        role = seed_roles[0]
        response = await client.delete(
            f"/api/roles/{role.id}",
            headers=viewer_auth_headers,
        )

        assert response.status_code == 403


class TestAssignRole:
    """Tests for assigning roles to users."""

    @pytest.mark.asyncio
    async def test_assign_role_to_user(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict,
        seed_roles: list[Role],
    ):
        """Test assigning a role to a user."""
        # Create a target user
        target_user = User(
            email="assignee@example.com",
            hashed_password=get_password_hash("password123"),
            full_name="Role Assignee",
            is_active=True,
        )
        db_session.add(target_user)
        await db_session.commit()
        await db_session.refresh(target_user)

        manager_role = next(r for r in seed_roles if r.name == "manager")

        response = await client.post(
            "/api/roles/assign",
            headers=admin_auth_headers,
            json={
                "user_id": target_user.id,
                "role_id": manager_role.id,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == target_user.id
        assert data["role_id"] == manager_role.id
        assert data["role"]["name"] == "manager"

    @pytest.mark.asyncio
    async def test_assign_role_non_admin_forbidden(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        viewer_auth_headers: dict,
        seed_roles: list[Role],
    ):
        """Test that non-admin users cannot assign roles (403)."""
        response = await client.post(
            "/api/roles/assign",
            headers=viewer_auth_headers,
            json={
                "user_id": 1,
                "role_id": seed_roles[0].id,
            },
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_assign_nonexistent_role_fails(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict,
        seed_roles: list[Role],
    ):
        """Test assigning a non-existent role returns 404."""
        response = await client.post(
            "/api/roles/assign",
            headers=admin_auth_headers,
            json={
                "user_id": 1,
                "role_id": 99999,
            },
        )

        assert response.status_code == 404


class TestGetUserRole:
    """Tests for getting a user's role."""

    @pytest.mark.asyncio
    async def test_get_user_role(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict,
        test_admin_user: User,
        seed_roles: list[Role],
    ):
        """Test getting a user's assigned role."""
        response = await client.get(
            f"/api/roles/user/{test_admin_user.id}",
            headers=admin_auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "admin"


class TestGetMyPermissions:
    """Tests for getting current user's permissions."""

    @pytest.mark.asyncio
    async def test_get_my_permissions(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict,
        test_admin_user: User,
        seed_roles: list[Role],
    ):
        """Test getting current user's effective permissions."""
        response = await client.get(
            "/api/roles/me/permissions",
            headers=admin_auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "role" in data
        assert "permissions" in data
        assert data["role"] == "admin"

    @pytest.mark.asyncio
    async def test_get_my_permissions_unauthorized(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Test getting permissions without auth returns 401."""
        response = await client.get("/api/roles/me/permissions")
        assert response.status_code == 401


class TestPermissionEnforcement:
    """Tests verifying permission enforcement on role management endpoints."""

    @pytest.mark.asyncio
    async def test_viewer_cannot_create_role(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        viewer_auth_headers: dict,
        seed_roles: list[Role],
    ):
        """Test viewer user gets 403 when trying to create a role."""
        response = await client.post(
            "/api/roles",
            headers=viewer_auth_headers,
            json={
                "name": "unauthorized_role",
                "permissions": {},
            },
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_sales_rep_cannot_manage_roles(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        sales_rep_auth_headers: dict,
        seed_roles: list[Role],
    ):
        """Test sales rep user gets 403 when trying to manage roles."""
        response = await client.post(
            "/api/roles",
            headers=sales_rep_auth_headers,
            json={
                "name": "salesrep_role",
                "permissions": {},
            },
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_manager_cannot_manage_roles(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        manager_auth_headers: dict,
        seed_roles: list[Role],
    ):
        """Test manager user gets 403 when trying to manage roles."""
        response = await client.post(
            "/api/roles",
            headers=manager_auth_headers,
            json={
                "name": "manager_role",
                "permissions": {},
            },
        )

        assert response.status_code == 403
