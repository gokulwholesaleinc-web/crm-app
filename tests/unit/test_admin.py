"""
Unit tests for admin dashboard endpoints.

Tests all admin endpoints: user listing, user update, deactivation,
system stats, team overview, activity feed, and role assignment.
"""

import pytest
from datetime import datetime, timedelta, timezone
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.auth.security import get_password_hash, create_access_token
from src.contacts.models import Contact
from src.companies.models import Company
from src.leads.models import Lead, LeadSource
from src.opportunities.models import Opportunity, PipelineStage
from src.audit.models import AuditLog


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
