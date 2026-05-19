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
from src.auth.models import User
from src.auth.security import create_access_token


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
        assert "state" in data
        assert "connected" in data
        assert "calendar_id" in data
        assert "last_synced_at" in data
        assert "synced_events_count" in data
        assert "last_error" in data

    @pytest.mark.asyncio
    async def test_status_state_disconnected_with_no_credential(
        self, client: AsyncClient, test_user,
    ):
        """No credential row → state=disconnected (distinct from needs_reconnect)."""
        response = await client.get(
            "/api/integrations/google-calendar/status",
            headers=_token(test_user),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["state"] == "disconnected"
        assert data["connected"] is False
        assert data["last_error"] is None

    @pytest.mark.asyncio
    async def test_status_state_needs_reconnect_when_credential_inactive(
        self, client: AsyncClient, db_session, test_user,
    ):
        """is_active=False on the credential ≡ Google revoked us → needs_reconnect."""
        from src.integrations.google_calendar.models import GoogleCalendarCredential
        db_session.add(GoogleCalendarCredential(
            user_id=test_user.id,
            access_token="",
            refresh_token="stale-refresh-token",
            calendar_id="primary",
            is_active=False,
        ))
        await db_session.commit()

        response = await client.get(
            "/api/integrations/google-calendar/status",
            headers=_token(test_user),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["state"] == "needs_reconnect"
        assert data["connected"] is False
        assert data["last_error"] is not None
        assert "reconnect" in data["last_error"].lower()

    @pytest.mark.asyncio
    async def test_sync_fast_paths_to_200_on_inactive_credential(
        self, client: AsyncClient, db_session, test_user,
    ):
        """Inactive credential → sync fast-paths to 200/empty; /status keeps reporting needs_reconnect."""
        from src.integrations.google_calendar.models import GoogleCalendarCredential
        # Simulates the post-invalid_grant state: refresh_access_token has
        # already flipped is_active=False (via _mark_revoked). Subsequent
        # sync calls don't need to round-trip to Google again — they
        # short-circuit on the is_active gate and let /status drive the UX.
        db_session.add(GoogleCalendarCredential(
            user_id=test_user.id,
            access_token="",
            refresh_token=None,
            calendar_id="primary",
            is_active=False,
        ))
        await db_session.commit()

        response = await client.post(
            "/api/integrations/google-calendar/sync",
            headers=_token(test_user),
        )
        assert response.status_code == 200
        status = await client.get(
            "/api/integrations/google-calendar/status",
            headers=_token(test_user),
        )
        assert status.json()["state"] == "needs_reconnect"

    @pytest.mark.asyncio
    async def test_refresh_access_token_invalid_grant_marks_revoked(
        self, db_session, test_user, monkeypatch,
    ):
        """Google 400 invalid_grant → credential.is_active=False + GoogleCalendarAuthError raised."""
        import httpx
        from src.integrations.google_calendar import service as svc_module
        from src.integrations.google_calendar.models import GoogleCalendarCredential
        from src.integrations.google_calendar.service import (
            GoogleCalendarAuthError,
            GoogleCalendarService,
        )

        credential = GoogleCalendarCredential(
            user_id=test_user.id,
            access_token="stale-access",
            refresh_token="revoked-refresh",
            calendar_id="primary",
            is_active=True,
        )
        db_session.add(credential)
        await db_session.commit()
        await db_session.refresh(credential)

        # Mock the HTTP layer (not the service) via httpx.MockTransport,
        # same pattern as the Gmail OAuth tests. Returns Google's actual
        # 400 invalid_grant body so refresh_access_token exercises the
        # _FATAL_OAUTH_ERROR_CODES path end-to-end.
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, json={
                "error": "invalid_grant",
                "error_description": "Token has been expired or revoked.",
            })

        transport = httpx.MockTransport(handler)

        class _PatchedAsyncClient(httpx.AsyncClient):
            def __init__(self, *a, **kw):
                kw["transport"] = transport
                super().__init__(*a, **kw)

        monkeypatch.setattr(svc_module.httpx, "AsyncClient", _PatchedAsyncClient)

        service = GoogleCalendarService(db_session)
        with pytest.raises(GoogleCalendarAuthError):
            await service.refresh_access_token(credential)

        # _mark_revoked commits explicitly so the flip survives the raise
        # (otherwise get_db's rollback-on-yield-exception would undo it).
        await db_session.refresh(credential)
        assert credential.is_active is False
        assert credential.access_token == ""

    @pytest.mark.asyncio
    async def test_refresh_access_token_transient_error_does_not_revoke(
        self, db_session, test_user, monkeypatch,
    ):
        """Google 400 with non-fatal error code → credential stays active, user can retry."""
        import httpx
        from src.integrations.google_calendar import service as svc_module
        from src.integrations.google_calendar.models import GoogleCalendarCredential
        from src.integrations.google_calendar.service import GoogleCalendarService

        credential = GoogleCalendarCredential(
            user_id=test_user.id,
            access_token="stale-access",
            refresh_token="working-refresh",
            calendar_id="primary",
            is_active=True,
        )
        db_session.add(credential)
        await db_session.commit()
        await db_session.refresh(credential)

        # Google blip: 400 with HTML body (e.g., LB error page misrouted).
        # Without the fatal-codes filter we'd force-reconnect on a Google
        # outage; this test pins the new behavior.
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, text="<html>Bad Gateway</html>")

        transport = httpx.MockTransport(handler)

        class _PatchedAsyncClient(httpx.AsyncClient):
            def __init__(self, *a, **kw):
                kw["transport"] = transport
                super().__init__(*a, **kw)

        monkeypatch.setattr(svc_module.httpx, "AsyncClient", _PatchedAsyncClient)

        service = GoogleCalendarService(db_session)
        with pytest.raises(httpx.HTTPStatusError):
            await service.refresh_access_token(credential)

        await db_session.refresh(credential)
        assert credential.is_active is True, (
            "transient 400 from Google must NOT flip is_active — that would "
            "force every user to reconnect during a Google outage"
        )


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


# =========================================================================
# _event_to_activity Tests — regression: Activity requires entity_type/entity_id
# =========================================================================

class TestEventToActivity:
    """Google events synced into CRM must satisfy Activity's NOT NULL columns."""

    @pytest.mark.asyncio
    async def test_timed_event_sets_entity_and_scheduled_at(
        self, db_session, test_user,
    ):
        from src.integrations.google_calendar.service import GoogleCalendarService

        service = GoogleCalendarService(db_session)
        activity = service._event_to_activity(
            event={
                "id": "abc123",
                "summary": "Client call",
                "description": "Quarterly review",
                "start": {"dateTime": "2026-05-01T15:00:00Z"},
            },
            user_id=test_user.id,
        )

        assert activity.entity_type == "users"
        assert activity.entity_id == test_user.id
        assert activity.scheduled_at is not None

        db_session.add(activity)
        await db_session.flush()
        assert activity.id is not None

    @pytest.mark.asyncio
    async def test_all_day_event_sets_entity_and_due_date(
        self, db_session, test_user,
    ):
        from src.integrations.google_calendar.service import GoogleCalendarService

        service = GoogleCalendarService(db_session)
        activity = service._event_to_activity(
            event={
                "id": "def456",
                "summary": "Holiday",
                "start": {"date": "2026-07-04"},
            },
            user_id=test_user.id,
        )

        assert activity.entity_type == "users"
        assert activity.entity_id == test_user.id
        assert activity.due_date is not None
        assert activity.scheduled_at is None

        db_session.add(activity)
        await db_session.flush()
        assert activity.id is not None


# =========================================================================
# Pagination Tests
# =========================================================================

class TestSyncPagination:
    """sync_from_google must paginate at Google's 2500/page ceiling."""

    def test_page_size_is_google_api_max(self):
        from src.integrations.google_calendar.service import GOOGLE_CALENDAR_PAGE_SIZE
        assert GOOGLE_CALENDAR_PAGE_SIZE == 2500


class TestSyncHorizon:
    """sync_from_google must cap timeMax to prevent recurring-event explosion."""

    def test_horizon_is_90_days(self):
        from src.integrations.google_calendar.service import CALENDAR_SYNC_HORIZON_DAYS
        assert CALENDAR_SYNC_HORIZON_DAYS == 90

    @pytest.mark.asyncio
    async def test_sync_without_connection_still_returns_empty(
        self, client: AsyncClient, test_user,
    ):
        """timeMax cap shouldn't break the no-connection fast path."""
        response = await client.post(
            "/api/integrations/google-calendar/sync",
            headers=_token(test_user),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["synced"] == 0
        assert data["events"] == []


# =========================================================================
# login_hint Tests
# =========================================================================

class TestGoogleCalendarLoginHint:
    """Test that login_hint=<user-email> is embedded in the OAuth authorize URL."""

    @pytest.mark.asyncio
    async def test_connect_endpoint_login_hint_in_auth_url(
        self, client: AsyncClient, test_user,
    ):
        """POST /connect with GOOGLE_CLIENT_ID set returns auth_url with login_hint.

        Uses monkeypatching on settings so the router passes the 400 guard and
        actually builds the URL. Verifies the endpoint wires current_user.email
        through to the URL — the integration between the router and service.
        """
        from urllib.parse import parse_qs, urlparse

        from src.config import settings as real_settings

        original = getattr(real_settings, "GOOGLE_CLIENT_ID", "")
        try:
            real_settings.GOOGLE_CLIENT_ID = "test-client-id"
            response = await client.post(
                "/api/integrations/google-calendar/connect",
                json={"redirect_uri": "http://localhost:3000/callback"},
                headers=_token(test_user),
            )
        finally:
            real_settings.GOOGLE_CLIENT_ID = original

        assert response.status_code == 200, response.text
        auth_url = response.json()["auth_url"]
        parsed = urlparse(auth_url)
        params = parse_qs(parsed.query)
        assert "login_hint" in params, f"login_hint missing from auth_url: {auth_url}"
        # test_user email is testuser@example.com
        assert params["login_hint"] == ["testuser@example.com"]
