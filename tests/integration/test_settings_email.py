"""Integration tests for GET/PUT /api/settings/email."""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.auth.security import get_password_hash, create_access_token
from src.roles.models import Role, UserRole, RoleName, DEFAULT_PERMISSIONS


# ---------------------------------------------------------------------------
# Extra fixtures not in conftest (non-superuser admin role user)
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(scope="function")
async def _non_superuser_admin_user(db_session: AsyncSession, seed_roles: list) -> User:
    """Admin-role user with is_superuser=False (to verify PUT gates on is_superuser)."""
    user = User(
        email="nonsuperadmin@example.com",
        hashed_password=get_password_hash("password123"),
        full_name="Non-Super Admin",
        is_active=True,
        is_superuser=False,
    )
    db_session.add(user)
    await db_session.flush()
    admin_role = next(r for r in seed_roles if r.name == "admin")
    db_session.add(UserRole(user_id=user.id, role_id=admin_role.id))
    await db_session.commit()
    await db_session.refresh(user)
    return user


def _headers(user: User) -> dict:
    token = create_access_token(data={"sub": str(user.id)})
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# GET /api/settings/email
# ---------------------------------------------------------------------------

class TestGetEmailSettings:
    async def test_no_auth_returns_401(self, client: AsyncClient):
        """Unauthenticated request is rejected."""
        resp = await client.get("/api/settings/email")
        assert resp.status_code == 401

    async def test_viewer_returns_403(self, client: AsyncClient, _viewer_user: User):
        """Viewer role cannot read email settings."""
        resp = await client.get("/api/settings/email", headers=_headers(_viewer_user))
        assert resp.status_code == 403

    async def test_sales_rep_returns_403(self, client: AsyncClient, _sales_rep_user: User):
        """Sales rep role cannot read email settings."""
        resp = await client.get("/api/settings/email", headers=_headers(_sales_rep_user))
        assert resp.status_code == 403

    async def test_manager_returns_200_with_schema(self, client: AsyncClient, _manager_user: User):
        """Manager gets full EmailSettingsResponse schema."""
        resp = await client.get("/api/settings/email", headers=_headers(_manager_user))
        assert resp.status_code == 200
        body = resp.json()
        assert "id" in body
        assert "daily_send_limit" in body
        assert "warmup_enabled" in body
        assert "warmup_target_daily" in body

    async def test_admin_returns_200(self, client: AsyncClient, test_admin_user: User):
        """Admin (is_superuser=True) can read email settings."""
        resp = await client.get("/api/settings/email", headers=_headers(test_admin_user))
        assert resp.status_code == 200

    async def test_superuser_returns_200(self, client: AsyncClient, test_superuser: User):
        """Superuser can read email settings."""
        resp = await client.get("/api/settings/email", headers=_headers(test_superuser))
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# PUT /api/settings/email
# ---------------------------------------------------------------------------

class TestUpdateEmailSettings:
    async def test_no_auth_returns_401(self, client: AsyncClient):
        """Unauthenticated PUT is rejected."""
        resp = await client.put("/api/settings/email", json={"daily_send_limit": 100})
        assert resp.status_code == 401

    async def test_manager_returns_403(self, client: AsyncClient, _manager_user: User):
        """Manager cannot write email settings (superuser-only)."""
        resp = await client.put(
            "/api/settings/email",
            json={"daily_send_limit": 50},
            headers=_headers(_manager_user),
        )
        assert resp.status_code == 403

    async def test_non_superuser_admin_returns_403(
        self, client: AsyncClient, _non_superuser_admin_user: User
    ):
        """Admin role without is_superuser flag cannot write email settings."""
        resp = await client.put(
            "/api/settings/email",
            json={"daily_send_limit": 50},
            headers=_headers(_non_superuser_admin_user),
        )
        assert resp.status_code == 403

    async def test_superuser_can_update_and_values_persist(
        self, client: AsyncClient, test_superuser: User
    ):
        """Superuser PUT returns updated values; subsequent GET reflects them."""
        payload = {"daily_send_limit": 999, "warmup_enabled": True, "warmup_target_daily": 500}
        put_resp = await client.put(
            "/api/settings/email", json=payload, headers=_headers(test_superuser)
        )
        assert put_resp.status_code == 200
        body = put_resp.json()
        assert body["daily_send_limit"] == 999
        assert body["warmup_enabled"] is True
        assert body["warmup_target_daily"] == 500

        get_resp = await client.get("/api/settings/email", headers=_headers(test_superuser))
        assert get_resp.status_code == 200
        assert get_resp.json()["daily_send_limit"] == 999

    async def test_invalid_payload_returns_422(self, client: AsyncClient, test_superuser: User):
        """Bogus field types are rejected with 422."""
        resp = await client.put(
            "/api/settings/email",
            json={"daily_send_limit": "not-a-number", "warmup_start_date": 12345},
            headers=_headers(test_superuser),
        )
        assert resp.status_code == 422
