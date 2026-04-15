"""
Unit tests for admin dashboard endpoints.

Tests all admin endpoints: user listing, user update, deactivation,
system stats, team overview, activity feed, and role assignment.
"""

import pytest
import pytest_asyncio
from datetime import datetime, timedelta, timezone
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import select

from src.auth.models import User
from src.auth.security import get_password_hash, create_access_token
from src.contacts.models import Contact
from src.companies.models import Company
from src.leads.models import Lead, LeadSource
from src.opportunities.models import Opportunity, PipelineStage
from src.audit.models import AuditLog
from src.whitelabel.models import Tenant, TenantUser


@pytest.fixture
def admin_headers(test_superuser: User) -> dict:
    """Create auth headers for a superuser."""
    token = create_access_token(data={"sub": str(test_superuser.id)})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def non_admin_headers(test_user: User) -> dict:
    """Create auth headers for a regular non-admin user."""
    token = create_access_token(data={"sub": str(test_user.id)})
    return {"Authorization": f"Bearer {token}"}


class TestAdminUsersEndpoint:
    """Tests for GET /api/admin/users."""

    @pytest.mark.asyncio
    async def test_list_users_as_admin(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_headers: dict,
        test_superuser: User,
    ):
        """Admin can list all users."""
        response = await client.get("/api/admin/users", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        user = data[0]
        assert "id" in user
        assert "email" in user
        assert "full_name" in user
        assert "role" in user
        assert "is_active" in user
        assert "lead_count" in user
        assert "contact_count" in user
        assert "opportunity_count" in user

    @pytest.mark.asyncio
    async def test_list_users_forbidden_for_regular_user(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        non_admin_headers: dict,
        test_user: User,
    ):
        """Regular user cannot access admin users endpoint."""
        response = await client.get("/api/admin/users", headers=non_admin_headers)
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_list_users_includes_record_counts(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_headers: dict,
        test_superuser: User,
        test_lead: Lead,
        test_contact: Contact,
        test_opportunity: Opportunity,
    ):
        """User record counts reflect owned entities."""
        response = await client.get("/api/admin/users", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        # The test_user who owns these records should show counts > 0
        owners_with_records = [u for u in data if u["lead_count"] > 0 or u["contact_count"] > 0]
        assert len(owners_with_records) >= 1


class TestAdminUpdateUser:
    """Tests for PATCH /api/admin/users/{id}."""

    @pytest.mark.asyncio
    async def test_update_user_role(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_headers: dict,
        test_superuser: User,
        test_user: User,
    ):
        """Admin can update a user's role."""
        response = await client.patch(
            f"/api/admin/users/{test_user.id}",
            json={"role": "manager"},
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "manager"

    @pytest.mark.asyncio
    async def test_update_role_invalidates_auth_cache(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_headers: dict,
        test_superuser: User,
        test_user: User,
    ):
        """Role changes must flush the 30s auth cache so new perms take effect immediately."""
        from src.auth.dependencies import _user_cache
        _user_cache[test_user.id] = test_user

        response = await client.patch(
            f"/api/admin/users/{test_user.id}",
            json={"role": "manager"},
            headers=admin_headers,
        )

        assert response.status_code == 200
        assert test_user.id not in _user_cache

    @pytest.mark.asyncio
    async def test_deactivate_user_via_patch(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_headers: dict,
        test_superuser: User,
        test_user: User,
    ):
        """Admin can deactivate a user via PATCH."""
        response = await client.patch(
            f"/api/admin/users/{test_user.id}",
            json={"is_active": False},
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["is_active"] is False

    @pytest.mark.asyncio
    async def test_update_nonexistent_user(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_headers: dict,
        test_superuser: User,
    ):
        """Updating a nonexistent user returns 404."""
        response = await client.patch(
            "/api/admin/users/99999",
            json={"role": "viewer"},
            headers=admin_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_user_forbidden_for_regular_user(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        non_admin_headers: dict,
        test_user: User,
    ):
        """Regular user cannot update other users."""
        response = await client.patch(
            f"/api/admin/users/{test_user.id}",
            json={"role": "admin"},
            headers=non_admin_headers,
        )
        assert response.status_code == 403


    @pytest.mark.asyncio
    async def test_update_user_email(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_headers: dict,
        test_superuser: User,
        test_user: User,
    ):
        """Admin can update a user's email."""
        response = await client.patch(
            f"/api/admin/users/{test_user.id}",
            json={"email": "newemail@example.com"},
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "newemail@example.com"

    @pytest.mark.asyncio
    async def test_update_user_full_name(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_headers: dict,
        test_superuser: User,
        test_user: User,
    ):
        """Admin can update a user's full name."""
        response = await client.patch(
            f"/api/admin/users/{test_user.id}",
            json={"full_name": "New Name"},
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["full_name"] == "New Name"

    @pytest.mark.asyncio
    async def test_update_user_email_duplicate_rejected(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_headers: dict,
        test_superuser: User,
        test_user: User,
    ):
        """Updating email to one already in use returns 409."""
        response = await client.patch(
            f"/api/admin/users/{test_user.id}",
            json={"email": test_superuser.email},
            headers=admin_headers,
        )
        assert response.status_code == 409
        assert "already in use" in response.json()["detail"].lower()


class TestAdminDeleteUser:
    """Tests for DELETE /api/admin/users/{id} (soft-delete)."""

    @pytest.mark.asyncio
    async def test_soft_delete_user(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_headers: dict,
        test_superuser: User,
        test_user: User,
    ):
        """Admin can soft-delete (deactivate) a user."""
        response = await client.delete(
            f"/api/admin/users/{test_user.id}",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "deactivated" in data["detail"].lower()

    @pytest.mark.asyncio
    async def test_soft_delete_nonexistent_user(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_headers: dict,
        test_superuser: User,
    ):
        """Deleting a nonexistent user returns 404."""
        response = await client.delete(
            "/api/admin/users/99999",
            headers=admin_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_soft_delete_forbidden_for_regular_user(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        non_admin_headers: dict,
        test_user: User,
    ):
        """Regular user cannot delete users."""
        response = await client.delete(
            f"/api/admin/users/{test_user.id}",
            headers=non_admin_headers,
        )
        assert response.status_code == 403


class TestAdminPermanentDeleteUser:
    """Tests for DELETE /api/admin/users/{id}/permanent (hard delete)."""

    @pytest.mark.asyncio
    async def test_permanent_delete_user(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_headers: dict,
        test_superuser: User,
    ):
        """Admin can permanently delete a user."""
        target = User(
            email="deleteme@example.com",
            hashed_password=get_password_hash("password123"),
            full_name="Delete Me",
            is_active=True,
            is_superuser=False,
        )
        db_session.add(target)
        await db_session.commit()
        await db_session.refresh(target)

        response = await client.delete(
            f"/api/admin/users/{target.id}/permanent",
            headers=admin_headers,
        )
        assert response.status_code == 200
        assert "permanently deleted" in response.json()["detail"].lower()

        # Confirm user no longer exists
        result = await db_session.execute(select(User).where(User.id == target.id))
        assert result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_permanent_delete_nonexistent_user(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_headers: dict,
        test_superuser: User,
    ):
        """Deleting a nonexistent user returns 404."""
        response = await client.delete(
            "/api/admin/users/99999/permanent",
            headers=admin_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_permanent_delete_forbidden_for_regular_user(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        non_admin_headers: dict,
        test_user: User,
    ):
        """Regular user cannot permanently delete users."""
        response = await client.delete(
            f"/api/admin/users/{test_user.id}/permanent",
            headers=non_admin_headers,
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_cannot_delete_self(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_headers: dict,
        test_superuser: User,
    ):
        """Admin cannot delete their own account."""
        response = await client.delete(
            f"/api/admin/users/{test_superuser.id}/permanent",
            headers=admin_headers,
        )
        assert response.status_code == 400
        assert "own account" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_cannot_delete_superuser(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_headers: dict,
        test_superuser: User,
    ):
        """Cannot permanently delete a superuser account."""
        other_super = User(
            email="othersuper@example.com",
            hashed_password=get_password_hash("password123"),
            full_name="Other Super",
            is_active=True,
            is_superuser=True,
        )
        db_session.add(other_super)
        await db_session.commit()
        await db_session.refresh(other_super)

        response = await client.delete(
            f"/api/admin/users/{other_super.id}/permanent",
            headers=admin_headers,
        )
        assert response.status_code == 400
        assert "superuser" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_permanent_delete_user_with_owned_records(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_headers: dict,
        test_superuser: User,
    ):
        """Deleting a user who owns records succeeds without errors."""
        target = User(
            email="ownerstuff@example.com",
            hashed_password=get_password_hash("password123"),
            full_name="Owner Stuff",
            is_active=True,
            is_superuser=False,
        )
        db_session.add(target)
        await db_session.commit()
        await db_session.refresh(target)

        contact = Contact(
            first_name="Orphan",
            last_name="Contact",
            email="orphan@test.com",
            status="active",
            owner_id=target.id,
            created_by_id=target.id,
        )
        db_session.add(contact)
        await db_session.commit()

        response = await client.delete(
            f"/api/admin/users/{target.id}/permanent",
            headers=admin_headers,
        )
        assert response.status_code == 200
        assert "permanently deleted" in response.json()["detail"].lower()

        # User should be gone
        result = await db_session.execute(select(User).where(User.id == target.id))
        assert result.scalar_one_or_none() is None


class TestAdminStats:
    """Tests for GET /api/admin/stats."""

    @pytest.mark.asyncio
    async def test_get_stats_empty_db(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_headers: dict,
        test_superuser: User,
    ):
        """Stats endpoint returns zeroes on near-empty db."""
        response = await client.get("/api/admin/stats", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert "total_users" in data
        assert "total_contacts" in data
        assert "total_companies" in data
        assert "total_leads" in data
        assert "total_opportunities" in data
        assert "total_quotes" in data
        assert "total_proposals" in data
        assert "total_payments" in data
        assert "active_users_7d" in data
        # At minimum we have the superuser
        assert data["total_users"] >= 1

    @pytest.mark.asyncio
    async def test_get_stats_with_data(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_headers: dict,
        test_superuser: User,
        test_lead: Lead,
        test_contact: Contact,
        test_company: Company,
        test_opportunity: Opportunity,
    ):
        """Stats reflect existing data."""
        response = await client.get("/api/admin/stats", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total_leads"] >= 1
        assert data["total_contacts"] >= 1
        assert data["total_companies"] >= 1
        assert data["total_opportunities"] >= 1

    @pytest.mark.asyncio
    async def test_stats_forbidden_for_regular_user(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        non_admin_headers: dict,
        test_user: User,
    ):
        """Regular user cannot access stats."""
        response = await client.get("/api/admin/stats", headers=non_admin_headers)
        assert response.status_code == 403


class TestAdminTeamOverview:
    """Tests for GET /api/admin/team-overview."""

    @pytest.mark.asyncio
    async def test_team_overview(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_headers: dict,
        test_superuser: User,
    ):
        """Team overview returns list of active users."""
        response = await client.get("/api/admin/team-overview", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        member = data[0]
        assert "user_id" in member
        assert "user_name" in member
        assert "role" in member
        assert "lead_count" in member
        assert "opportunity_count" in member
        assert "total_pipeline_value" in member
        assert "won_deals" in member

    @pytest.mark.asyncio
    async def test_team_overview_forbidden_for_regular_user(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        non_admin_headers: dict,
        test_user: User,
    ):
        """Regular user cannot access team overview."""
        response = await client.get("/api/admin/team-overview", headers=non_admin_headers)
        assert response.status_code == 403


class TestAdminActivityFeed:
    """Tests for GET /api/admin/activity-feed."""

    @pytest.mark.asyncio
    async def test_activity_feed_empty(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_headers: dict,
        test_superuser: User,
    ):
        """Activity feed returns empty list when no audit logs exist."""
        response = await client.get("/api/admin/activity-feed", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_activity_feed_with_entries(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_headers: dict,
        test_superuser: User,
    ):
        """Activity feed returns audit log entries."""
        # Create an audit log entry directly
        entry = AuditLog(
            entity_type="lead",
            entity_id=1,
            user_id=test_superuser.id,
            action="create",
            changes={"field": "status", "old_value": None, "new_value": "new"},
        )
        db_session.add(entry)
        await db_session.commit()

        response = await client.get("/api/admin/activity-feed", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert data[0]["entity_type"] == "lead"
        assert data[0]["action"] == "create"
        assert data[0]["user_name"] is not None

    @pytest.mark.asyncio
    async def test_activity_feed_forbidden_for_regular_user(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        non_admin_headers: dict,
        test_user: User,
    ):
        """Regular user cannot access activity feed."""
        response = await client.get("/api/admin/activity-feed", headers=non_admin_headers)
        assert response.status_code == 403


class TestAdminAssignRole:
    """Tests for POST /api/admin/users/{id}/assign-role."""

    @pytest.mark.asyncio
    async def test_assign_valid_role(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_headers: dict,
        test_superuser: User,
        test_user: User,
    ):
        """Admin can assign a valid role to a user."""
        response = await client.post(
            f"/api/admin/users/{test_user.id}/assign-role",
            json={"role": "manager"},
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "manager"

    @pytest.mark.asyncio
    async def test_assign_invalid_role(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_headers: dict,
        test_superuser: User,
        test_user: User,
    ):
        """Assigning an invalid role returns 400."""
        response = await client.post(
            f"/api/admin/users/{test_user.id}/assign-role",
            json={"role": "superadmin"},
            headers=admin_headers,
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_assign_role_to_nonexistent_user(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_headers: dict,
        test_superuser: User,
    ):
        """Assigning a role to nonexistent user returns 404."""
        response = await client.post(
            "/api/admin/users/99999/assign-role",
            json={"role": "viewer"},
            headers=admin_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_assign_role_forbidden_for_regular_user(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        non_admin_headers: dict,
        test_user: User,
    ):
        """Regular user cannot assign roles."""
        response = await client.post(
            f"/api/admin/users/{test_user.id}/assign-role",
            json={"role": "admin"},
            headers=non_admin_headers,
        )
        assert response.status_code == 403


class TestAdminRoleAccess:
    """Test that admin-role users (not just superusers) can access admin endpoints."""

    @pytest.mark.asyncio
    async def test_admin_role_can_access(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """A user with role=admin (not superuser) can access admin endpoints."""
        admin_user = User(
            email="roleadmin@example.com",
            hashed_password=get_password_hash("password123"),
            full_name="Role Admin",
            is_active=True,
            is_superuser=False,
            role="admin",
        )
        db_session.add(admin_user)
        await db_session.commit()
        await db_session.refresh(admin_user)

        token = create_access_token(data={"sub": str(admin_user.id)})
        headers = {"Authorization": f"Bearer {token}"}

        response = await client.get("/api/admin/stats", headers=headers)
        assert response.status_code == 200


class TestAdminLinkTenant:
    """Tests for POST /api/admin/users/{id}/link-tenant."""

    @pytest_asyncio.fixture
    async def default_tenant(self, db_session: AsyncSession) -> Tenant:
        """Create a default tenant for link-tenant tests."""
        tenant = Tenant(
            name="Default Organization",
            slug="default",
            is_active=True,
            plan="professional",
            max_users=50,
        )
        db_session.add(tenant)
        await db_session.commit()
        await db_session.refresh(tenant)
        return tenant

    @pytest.mark.asyncio
    async def test_link_user_to_tenant_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_headers: dict,
        test_superuser: User,
        test_user: User,
        default_tenant: Tenant,
    ):
        """Admin can link a user to a tenant."""
        response = await client.post(
            f"/api/admin/users/{test_user.id}/link-tenant",
            json={"tenant_slug": "default", "role": "member", "is_primary": True},
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == test_user.id
        assert data["tenant_slug"] == "default"
        assert data["role"] == "member"
        assert data["is_primary"] is True

    @pytest.mark.asyncio
    async def test_link_user_to_tenant_duplicate_rejected(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_headers: dict,
        test_superuser: User,
        test_user: User,
        default_tenant: Tenant,
    ):
        """Linking a user to a tenant they're already in returns 409."""
        # Link first time
        await client.post(
            f"/api/admin/users/{test_user.id}/link-tenant",
            json={"tenant_slug": "default"},
            headers=admin_headers,
        )
        # Duplicate link
        response = await client.post(
            f"/api/admin/users/{test_user.id}/link-tenant",
            json={"tenant_slug": "default"},
            headers=admin_headers,
        )
        assert response.status_code == 409
        assert "already linked" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_link_user_to_nonexistent_tenant(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_headers: dict,
        test_superuser: User,
        test_user: User,
    ):
        """Linking to a nonexistent tenant returns 404."""
        response = await client.post(
            f"/api/admin/users/{test_user.id}/link-tenant",
            json={"tenant_slug": "nonexistent"},
            headers=admin_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_link_nonexistent_user_to_tenant(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_headers: dict,
        test_superuser: User,
        default_tenant: Tenant,
    ):
        """Linking a nonexistent user returns 404."""
        response = await client.post(
            "/api/admin/users/99999/link-tenant",
            json={"tenant_slug": "default"},
            headers=admin_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_link_tenant_forbidden_for_regular_user(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        non_admin_headers: dict,
        test_user: User,
        default_tenant: Tenant,
    ):
        """Regular user cannot link users to tenants."""
        response = await client.post(
            f"/api/admin/users/{test_user.id}/link-tenant",
            json={"tenant_slug": "default"},
            headers=non_admin_headers,
        )
        assert response.status_code == 403


class TestCacheEndpointsRemoved:
    """Verify that admin cache management endpoints no longer exist."""

    @pytest.mark.asyncio
    async def test_cache_stats_endpoint_removed(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_headers: dict,
        test_superuser: User,
    ):
        """GET /api/admin/cache/stats should no longer be routable."""
        response = await client.get("/api/admin/cache/stats", headers=admin_headers)
        assert response.status_code in (404, 405)

    @pytest.mark.asyncio
    async def test_cache_clear_endpoint_removed(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_headers: dict,
        test_superuser: User,
    ):
        """POST /api/admin/cache/clear should no longer be routable."""
        response = await client.post("/api/admin/cache/clear", headers=admin_headers)
        assert response.status_code in (404, 405)

    @pytest.mark.asyncio
    async def test_cache_pattern_delete_endpoint_removed(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_headers: dict,
        test_superuser: User,
    ):
        """DELETE /api/admin/cache/{pattern} should no longer be routable."""
        response = await client.delete("/api/admin/cache/dashboard*", headers=admin_headers)
        assert response.status_code in (404, 405)

    def test_cache_schemas_not_in_admin_schemas(self):
        """CacheStatsResponse and CacheClearResponse should not exist in admin schemas."""
        from src.admin import schemas
        assert not hasattr(schemas, "CacheStatsResponse")
        assert not hasattr(schemas, "CacheClearResponse")
