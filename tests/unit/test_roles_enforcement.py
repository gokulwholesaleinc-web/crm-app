"""Permission enforcement & last-admin guard integration tests.

These exercise the gates we wired into contacts/companies/activities/
opportunities/campaigns/reports routers plus the LastAdminError raised
from ``RoleService.assign_role_to_user``.

Tests run against the real SQLite engine from ``conftest`` — no mocks.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.auth.security import create_access_token, get_password_hash
from src.contacts.models import Contact
from src.roles.models import Role, RoleName, UserRole


def _bearer(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(data={'sub': str(user.id)})}"}


# ---------------------------------------------------------------------------
# Contacts gate
# ---------------------------------------------------------------------------

class TestContactsPermissionGate:
    """Viewer (read-only) must be 403 on every contact write; manager 2xx."""

    @pytest.mark.asyncio
    async def test_viewer_cannot_create_contact(
        self,
        client: AsyncClient,
        viewer_auth_headers: dict,
        seed_roles: list[Role],
    ) -> None:
        """Viewer is denied POST /api/contacts."""
        response = await client.post(
            "/api/contacts",
            headers=viewer_auth_headers,
            json={"first_name": "Block", "last_name": "Me", "email": "block@me.test"},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_viewer_cannot_update_contact(
        self,
        client: AsyncClient,
        viewer_auth_headers: dict,
        test_contact: Contact,
        seed_roles: list[Role],
    ) -> None:
        """Viewer is denied PATCH /api/contacts/{id}."""
        response = await client.patch(
            f"/api/contacts/{test_contact.id}",
            headers=viewer_auth_headers,
            json={"first_name": "Updated"},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_viewer_cannot_delete_contact(
        self,
        client: AsyncClient,
        viewer_auth_headers: dict,
        test_contact: Contact,
        seed_roles: list[Role],
    ) -> None:
        """Viewer is denied DELETE /api/contacts/{id}."""
        response = await client.delete(
            f"/api/contacts/{test_contact.id}",
            headers=viewer_auth_headers,
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_manager_can_create_contact(
        self,
        client: AsyncClient,
        manager_auth_headers: dict,
        seed_roles: list[Role],
    ) -> None:
        """Manager has contacts:create — POST returns 201."""
        response = await client.post(
            "/api/contacts",
            headers=manager_auth_headers,
            json={
                "first_name": "Allowed",
                "last_name": "Manager",
                "email": "manager@example.com",
            },
        )
        assert response.status_code == 201, response.text


# ---------------------------------------------------------------------------
# Companies gate
# ---------------------------------------------------------------------------

class TestCompaniesPermissionGate:
    """Viewer denied; manager allowed (companies CRUD)."""

    @pytest.mark.asyncio
    async def test_viewer_cannot_create_company(
        self,
        client: AsyncClient,
        viewer_auth_headers: dict,
        seed_roles: list[Role],
    ) -> None:
        """Viewer is denied POST /api/companies."""
        response = await client.post(
            "/api/companies",
            headers=viewer_auth_headers,
            json={"name": "Blocked LLC"},
        )
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# Opportunities gate
# ---------------------------------------------------------------------------

# Opportunities permission gate retired with the /api/opportunities router
# (collapsed to leads-only pipeline 2026-05-14, PR #328).


# ---------------------------------------------------------------------------
# Activities gate
# ---------------------------------------------------------------------------

class TestActivitiesPermissionGate:
    """Viewer denied on write; sales_rep allowed."""

    @pytest.mark.asyncio
    async def test_viewer_cannot_create_activity(
        self,
        client: AsyncClient,
        viewer_auth_headers: dict,
        seed_roles: list[Role],
        test_contact: Contact,
    ) -> None:
        """Viewer is denied POST /api/activities."""
        response = await client.post(
            "/api/activities",
            headers=viewer_auth_headers,
            json={
                "activity_type": "call",
                "subject": "Should not insert",
                "entity_type": "contacts",
                "entity_id": test_contact.id,
            },
        )
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# Campaigns / Reports gates
# ---------------------------------------------------------------------------

class TestCampaignsReportsGate:
    """Viewer + sales_rep denied on writes (campaigns/reports are read-only
    for sales_rep per DEFAULT_PERMISSIONS)."""

    @pytest.mark.asyncio
    async def test_sales_rep_cannot_create_campaign(
        self,
        client: AsyncClient,
        sales_rep_auth_headers: dict,
        seed_roles: list[Role],
    ) -> None:
        """Sales rep is denied POST /api/campaigns (read-only on campaigns)."""
        response = await client.post(
            "/api/campaigns",
            headers=sales_rep_auth_headers,
            json={"name": "Should fail", "campaign_type": "email", "status": "planned"},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_sales_rep_cannot_create_saved_report(
        self,
        client: AsyncClient,
        sales_rep_auth_headers: dict,
        seed_roles: list[Role],
    ) -> None:
        """Sales rep is denied POST /api/reports (read-only on reports)."""
        response = await client.post(
            "/api/reports",
            headers=sales_rep_auth_headers,
            json={
                "name": "Blocked report",
                "entity_type": "leads",
                "metric": "count",
            },
        )
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# Last-active-admin guard
# ---------------------------------------------------------------------------

class TestLastActiveAdminGuard:
    """Server must refuse to demote the sole remaining active admin."""

    @pytest.mark.asyncio
    async def test_demoting_sole_admin_returns_400(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict,
        test_admin_user: User,
        seed_roles: list[Role],
    ) -> None:
        """Demoting the only admin via /api/roles/assign returns 400."""
        viewer_role = next(r for r in seed_roles if r.name == RoleName.VIEWER.value)

        response = await client.post(
            "/api/roles/assign",
            headers=admin_auth_headers,
            json={"user_id": test_admin_user.id, "role_id": viewer_role.id},
        )

        assert response.status_code == 400
        assert "last active admin" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_demoting_admin_with_peer_admin_succeeds(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict,
        test_admin_user: User,
        seed_roles: list[Role],
    ) -> None:
        """With a second active admin available, demotion goes through."""
        admin_role = next(r for r in seed_roles if r.name == RoleName.ADMIN.value)
        viewer_role = next(r for r in seed_roles if r.name == RoleName.VIEWER.value)

        peer_admin = User(
            email="peer_admin@example.com",
            hashed_password=get_password_hash("peerpass1234"),
            full_name="Peer Admin",
            is_active=True,
            is_superuser=False,
        )
        db_session.add(peer_admin)
        await db_session.flush()
        db_session.add(UserRole(user_id=peer_admin.id, role_id=admin_role.id))
        await db_session.commit()

        response = await client.post(
            "/api/roles/assign",
            headers=admin_auth_headers,
            json={"user_id": peer_admin.id, "role_id": viewer_role.id},
        )

        assert response.status_code == 200, response.text
        assert response.json()["role_id"] == viewer_role.id

    @pytest.mark.asyncio
    async def test_inactive_peer_admins_dont_count(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict,
        test_admin_user: User,
        seed_roles: list[Role],
    ) -> None:
        """An inactive peer admin does not satisfy the guard."""
        admin_role = next(r for r in seed_roles if r.name == RoleName.ADMIN.value)
        viewer_role = next(r for r in seed_roles if r.name == RoleName.VIEWER.value)

        deactivated = User(
            email="dead_admin@example.com",
            hashed_password=get_password_hash("deadpass1234"),
            full_name="Deactivated Admin",
            is_active=False,
            is_superuser=False,
        )
        db_session.add(deactivated)
        await db_session.flush()
        db_session.add(UserRole(user_id=deactivated.id, role_id=admin_role.id))
        await db_session.commit()

        response = await client.post(
            "/api/roles/assign",
            headers=admin_auth_headers,
            json={"user_id": test_admin_user.id, "role_id": viewer_role.id},
        )

        assert response.status_code == 400


# ---------------------------------------------------------------------------
# Recent Activities enrichment
# ---------------------------------------------------------------------------

class TestTimelineEnrichment:
    """The /timeline/user response must carry owner_name + entity_label so
    the dashboard widget can show the user and a clickable entity link."""

    @pytest.mark.asyncio
    async def test_user_timeline_includes_owner_and_entity_label(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_activity,
        test_contact: Contact,
    ) -> None:
        """Each item carries the activity owner's full_name and the linked entity's display label."""
        response = await client.get("/api/activities/timeline/user", headers=auth_headers)
        assert response.status_code == 200

        items = response.json()["items"]
        assert items, "expected at least one activity for test_user"
        target = next((i for i in items if i["id"] == test_activity.id), None)
        assert target is not None
        assert target["owner_name"] == test_user.full_name
        assert target["entity_type"] == "contacts"
        assert target["entity_id"] == test_contact.id
        # Contact label = "first_name last_name"
        expected_label = f"{test_contact.first_name} {test_contact.last_name}".strip()
        assert target["entity_label"] == expected_label
        assert target["entity_link"] == f"/contacts/{test_contact.id}"
