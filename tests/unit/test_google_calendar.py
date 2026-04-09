"""Tests for Google Calendar integration endpoints.

Validates:
- Connection status endpoint
- OAuth connect flow initiation
- Disconnect endpoint
- Sync endpoint
- Push endpoint
- Authentication requirements (401 without token)
- Request validation (422 on bad input)
- No mocking — uses real DB operations via in-memory SQLite
"""

import pytest
from httpx import AsyncClient

from src.auth.security import create_access_token
from src.auth.models import User


def _token(user: User) -> dict:
    token = create_access_token(data={"sub": str(user.id)})
    return {"Authorization": f"Bearer {token}"}


# =========================================================================
# Authentication Tests — all endpoints require auth
# =========================================================================

class TestGoogleCalendarAuth:
    """All Google Calendar endpoints should require authentication."""

    @pytest.mark.asyncio
    async def test_status_requires_auth(self, client: AsyncClient):
        """Should return 401 without authentication."""
        response = await client.get("/api/integrations/google-calendar/status")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_connect_requires_auth(self, client: AsyncClient):
        """Should return 401 without authentication."""
        response = await client.post(
            "/api/integrations/google-calendar/connect",
            json={},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_disconnect_requires_auth(self, client: AsyncClient):
        """Should return 401 without authentication."""
        response = await client.delete("/api/integrations/google-calendar/disconnect")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_sync_requires_auth(self, client: AsyncClient):
        """Should return 401 without authentication."""
        response = await client.post("/api/integrations/google-calendar/sync")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_push_requires_auth(self, client: AsyncClient):
        """Should return 401 without authentication."""
        response = await client.post(
            "/api/integrations/google-calendar/push",
            json={"activity_id": 1},
        )
        assert response.status_code == 401


# =========================================================================
# Status Endpoint Tests
# =========================================================================

class TestGoogleCalendarStatus:
    """Test GET /api/integrations/google-calendar/status."""

    @pytest.mark.asyncio
    async def test_status_returns_200(self, client: AsyncClient, test_user):
        """Should return status object for authenticated user with no connection."""
        response = await client.get(
            "/api/integrations/google-calendar/status",
            headers=_token(test_user),
        )
        assert response.status_code == 200
        data = response.json()
        assert "connected" in data
        assert data["connected"] is False
        assert "synced_events_count" in data

    @pytest.mark.asyncio
    async def test_status_returns_correct_fields(self, client: AsyncClient, test_user):
        """Status response should contain all expected fields."""
        response = await client.get(
            "/api/integrations/google-calendar/status",
            headers=_token(test_user),
        )
        assert response.status_code == 200
        data = response.json()
        assert "connected" in data
        assert "calendar_id" in data
        assert "last_synced_at" in data
        assert "synced_events_count" in data


# =========================================================================
# Connect Endpoint Tests
# =========================================================================

class TestGoogleCalendarConnect:
    """Test POST /api/integrations/google-calendar/connect."""

    @pytest.mark.asyncio
    async def test_connect_without_google_config_returns_400(
        self, client: AsyncClient, test_user,
    ):
        """Without GOOGLE_CLIENT_ID, connect should return 400."""
        response = await client.post(
            "/api/integrations/google-calendar/connect",
            json={},
            headers=_token(test_user),
        )
        assert response.status_code == 400
        assert "not configured" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_connect_accepts_redirect_uri(
        self, client: AsyncClient, test_user,
    ):
        """Should accept optional redirect_uri without 422."""
        response = await client.post(
            "/api/integrations/google-calendar/connect",
            json={"redirect_uri": "http://localhost:3000/settings/calendar/callback"},
            headers=_token(test_user),
        )
        # Without Google client ID, returns 400 — but NOT 422
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_connect_endpoint_exists(self, client: AsyncClient, test_user):
        """Endpoint should exist and not return 404 or 405."""
        response = await client.post(
            "/api/integrations/google-calendar/connect",
            json={},
            headers=_token(test_user),
        )
        assert response.status_code != 404
        assert response.status_code != 405


# =========================================================================
# Disconnect Endpoint Tests
# =========================================================================

class TestGoogleCalendarDisconnect:
    """Test DELETE /api/integrations/google-calendar/disconnect."""

    @pytest.mark.asyncio
    async def test_disconnect_no_connection_returns_404(
        self, client: AsyncClient, test_user,
    ):
        """Disconnecting when not connected should return 404."""
        response = await client.delete(
            "/api/integrations/google-calendar/disconnect",
            headers=_token(test_user),
        )
        assert response.status_code == 404
        assert "No Google Calendar connection found" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_disconnect_endpoint_exists(self, client: AsyncClient, test_user):
        """Endpoint should exist and not return 405."""
        response = await client.delete(
            "/api/integrations/google-calendar/disconnect",
            headers=_token(test_user),
        )
        assert response.status_code != 405


# =========================================================================
# Sync Endpoint Tests
# =========================================================================

class TestGoogleCalendarSync:
    """Test POST /api/integrations/google-calendar/sync."""

    @pytest.mark.asyncio
    async def test_sync_without_connection_returns_empty(
        self, client: AsyncClient, test_user,
    ):
        """Syncing without a connection should return 200 with zero synced events."""
        response = await client.post(
            "/api/integrations/google-calendar/sync",
            headers=_token(test_user),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["synced"] == 0
        assert data["events"] == []

    @pytest.mark.asyncio
    async def test_sync_endpoint_exists(self, client: AsyncClient, test_user):
        """Endpoint should exist and not return 404 or 405."""
        response = await client.post(
            "/api/integrations/google-calendar/sync",
            headers=_token(test_user),
        )
        assert response.status_code != 404
        assert response.status_code != 405


# =========================================================================
# Push Endpoint Tests
# =========================================================================

class TestGoogleCalendarPush:
    """Test POST /api/integrations/google-calendar/push."""

    @pytest.mark.asyncio
    async def test_push_requires_activity_id(self, client: AsyncClient, test_user):
        """Should return 422 when activity_id is missing."""
        response = await client.post(
            "/api/integrations/google-calendar/push",
            json={},
            headers=_token(test_user),
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_push_without_connection_returns_400(
        self, client: AsyncClient, test_user, test_activity,
    ):
        """Pushing a real activity without a Google Calendar connection should return 400."""
        response = await client.post(
            "/api/integrations/google-calendar/push",
            json={"activity_id": test_activity.id},
            headers=_token(test_user),
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_push_missing_activity_returns_404(
        self, client: AsyncClient, test_user,
    ):
        """Pushing a non-existent activity should return 404."""
        response = await client.post(
            "/api/integrations/google-calendar/push",
            json={"activity_id": 99999},
            headers=_token(test_user),
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_push_endpoint_exists(
        self, client: AsyncClient, test_user, test_activity,
    ):
        """Endpoint should exist and not return 404 or 405 for a real activity."""
        response = await client.post(
            "/api/integrations/google-calendar/push",
            json={"activity_id": test_activity.id},
            headers=_token(test_user),
        )
        assert response.status_code != 404
        assert response.status_code != 405
