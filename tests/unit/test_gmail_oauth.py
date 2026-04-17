"""Tests for Gmail OAuth endpoints.

Google HTTP calls are stubbed via httpx.MockTransport — real httpx code path runs
end-to-end, only the network layer is intercepted. DB is SQLite in-memory (real rows,
no business mocks).
"""

import base64
import json
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from sqlalchemy import select

from src.auth.models import User
from src.auth.security import create_access_token
from src.integrations.gmail.models import GmailConnection, GmailSyncState
from src.integrations.gmail.router import get_gmail_http_factory, GMAIL_OAUTH_STATE_COOKIE
from src.integrations.gmail import oauth as gmail_oauth
from src.main import app


# =============================================================================
# Helpers
# =============================================================================


def _auth_header(user: User) -> dict:
    token = create_access_token(data={"sub": str(user.id)})
    return {"Authorization": f"Bearer {token}"}


def _make_id_token(email: str) -> str:
    """Build a minimal JWT id_token (unsigned) with the given email."""
    payload = base64.urlsafe_b64encode(
        json.dumps({"sub": "fake-sub-123", "email": email}).encode()
    ).rstrip(b"=").decode()
    return f"header.{payload}.sig"


def _make_gmail_stub_factory(
    *,
    token_response: dict | None = None,
    token_status: int = 200,
    revoke_status: int = 200,
    captured: dict | None = None,
):
    """Return a client factory whose transport stubs Google's Gmail OAuth endpoints."""

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "oauth2.googleapis.com/token" in url:
            if captured is not None:
                captured["token_request"] = {
                    "body": dict(parse_qs(request.content.decode() or "")),
                }
            return httpx.Response(token_status, json=token_response or {})
        if "oauth2.googleapis.com/revoke" in url:
            if captured is not None:
                captured["revoke_url"] = url
                captured["revoke_params"] = dict(request.url.params)
            return httpx.Response(revoke_status, json={})
        return httpx.Response(404, json={"error": f"unexpected url: {url}"})

    transport = httpx.MockTransport(handler)

    def factory() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=transport)

    return factory


def _override_gmail_http_factory(factory):
    app.dependency_overrides[get_gmail_http_factory] = lambda: factory


def _clear_gmail_http_factory_override():
    app.dependency_overrides.pop(get_gmail_http_factory, None)


async def _prime_gmail_state(client, auth_headers: dict) -> str:
    """Call /authorize to get the state cookie and return the state value."""
    from src.config import settings
    original = settings.GOOGLE_CLIENT_ID
    settings.GOOGLE_CLIENT_ID = "test-client-id.apps.googleusercontent.com"
    try:
        resp = await client.get("/api/integrations/gmail/authorize", headers=auth_headers)
        assert resp.status_code == 200, resp.text
        return resp.json()["auth_url"].split("state=")[1].split("&")[0]
    finally:
        settings.GOOGLE_CLIENT_ID = original


# =============================================================================
# /authorize
# =============================================================================


class TestGmailAuthorize:
    @pytest.mark.asyncio
    async def test_sets_httponly_state_cookie(self, client, test_user):
        """authorize sets an HttpOnly cookie named crm_gmail_oauth_state."""
        from src.config import settings
        original = settings.GOOGLE_CLIENT_ID
        settings.GOOGLE_CLIENT_ID = "test-client-id.apps.googleusercontent.com"
        try:
            resp = await client.get(
                "/api/integrations/gmail/authorize",
                headers=_auth_header(test_user),
            )
            assert resp.status_code == 200
            cookie = resp.cookies.get(GMAIL_OAUTH_STATE_COOKIE)
            assert cookie is not None
            assert len(cookie) >= 16
        finally:
            settings.GOOGLE_CLIENT_ID = original

    @pytest.mark.asyncio
    async def test_samesite_none_in_prod(self, client, test_user):
        """In prod (DEBUG=False), cookie must be SameSite=None; Secure."""
        from src.config import settings
        original_debug = settings.DEBUG
        original_id = settings.GOOGLE_CLIENT_ID
        settings.DEBUG = False
        settings.GOOGLE_CLIENT_ID = "test-client-id.apps.googleusercontent.com"
        try:
            resp = await client.get(
                "/api/integrations/gmail/authorize",
                headers=_auth_header(test_user),
            )
            assert resp.status_code == 200
            set_cookie_header = resp.headers.get("set-cookie", "")
            assert "samesite=none" in set_cookie_header.lower()
        finally:
            settings.DEBUG = original_debug
            settings.GOOGLE_CLIENT_ID = original_id

    @pytest.mark.asyncio
    async def test_returns_auth_url_with_gmail_scopes(self, client, test_user):
        """auth_url must include gmail.send and gmail.readonly scopes."""
        from src.config import settings
        original = settings.GOOGLE_CLIENT_ID
        settings.GOOGLE_CLIENT_ID = "test-client-id.apps.googleusercontent.com"
        try:
            resp = await client.get(
                "/api/integrations/gmail/authorize",
                headers=_auth_header(test_user),
            )
            assert resp.status_code == 200
            auth_url = resp.json()["auth_url"]
            parsed = urlparse(auth_url)
            params = parse_qs(parsed.query)
            scope = params["scope"][0]
            assert "gmail.send" in scope
            assert "gmail.readonly" in scope
            assert "openid" in scope
            assert params["access_type"] == ["offline"]
            assert params["prompt"] == ["consent select_account"]
        finally:
            settings.GOOGLE_CLIENT_ID = original

    @pytest.mark.asyncio
    async def test_auth_url_omits_login_hint(self, client, test_user):
        """Gmail authorize must NOT send login_hint so Google shows the account picker.

        Regression guard: passing the CRM login email as login_hint caused Google to
        silently bind to the Chrome default account, blocking users from linking a
        different Gmail.
        """
        from src.config import settings
        original = settings.GOOGLE_CLIENT_ID
        settings.GOOGLE_CLIENT_ID = "test-client-id.apps.googleusercontent.com"
        try:
            resp = await client.get(
                "/api/integrations/gmail/authorize",
                headers=_auth_header(test_user),
            )
            assert resp.status_code == 200
            auth_url = resp.json()["auth_url"]
            params = parse_qs(urlparse(auth_url).query)
            assert "login_hint" not in params
        finally:
            settings.GOOGLE_CLIENT_ID = original

    @pytest.mark.asyncio
    async def test_requires_auth(self, client):
        """Unauthenticated request must be rejected."""
        resp = await client.get("/api/integrations/gmail/authorize")
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_missing_client_id_returns_400(self, client, test_user):
        from src.config import settings
        original = settings.GOOGLE_CLIENT_ID
        settings.GOOGLE_CLIENT_ID = ""
        try:
            resp = await client.get(
                "/api/integrations/gmail/authorize",
                headers=_auth_header(test_user),
            )
            assert resp.status_code == 400
            assert "not configured" in resp.json()["detail"].lower()
        finally:
            settings.GOOGLE_CLIENT_ID = original


# =============================================================================
# /callback
# =============================================================================


class TestGmailCallback:
    @pytest.fixture(autouse=True)
    def _debug_mode(self):
        from src.config import settings
        original = settings.DEBUG
        settings.DEBUG = True
        yield
        settings.DEBUG = original

    @pytest.mark.asyncio
    async def test_callback_upserts_connection_with_canonical_scopes(
        self, client, db_session, test_user
    ):
        """Callback with valid code+state upserts GmailConnection with canonical scopes."""
        from src.config import settings
        settings.GOOGLE_CLIENT_ID = "test-client-id.apps.googleusercontent.com"
        settings.GOOGLE_CLIENT_SECRET = "test-secret"

        gmail_email = "user@gmail.com"
        factory = _make_gmail_stub_factory(
            token_response={
                "access_token": "ya29.test-access",
                "refresh_token": "1//test-refresh",
                "expires_in": 3600,
                "id_token": _make_id_token(gmail_email),
                "token_type": "Bearer",
            }
        )
        _override_gmail_http_factory(factory)
        try:
            state = await _prime_gmail_state(client, _auth_header(test_user))
            resp = await client.post(
                "/api/integrations/gmail/callback",
                json={"code": "auth-code-123", "state": state},
                headers=_auth_header(test_user),
            )
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["email"] == gmail_email
            assert body["is_active"] is True
            assert body["scopes"] == ["openid", "email", "profile", "gmail.send", "gmail.readonly"]

            result = await db_session.execute(
                select(GmailConnection).where(GmailConnection.user_id == test_user.id)
            )
            conn = result.scalar_one()
            assert conn.scopes == "openid email profile gmail.send gmail.readonly"
            assert conn.revoked_at is None

            sync_result = await db_session.execute(
                select(GmailSyncState).where(GmailSyncState.user_id == test_user.id)
            )
            sync_state = sync_result.scalar_one()
            assert sync_state.last_history_id is None
        finally:
            _clear_gmail_http_factory_override()
            settings.GOOGLE_CLIENT_ID = ""
            settings.GOOGLE_CLIENT_SECRET = ""

    @pytest.mark.asyncio
    async def test_callback_state_mismatch_returns_400(self, client, test_user):
        """Callback without a matching state cookie must return 400."""
        from src.config import settings
        settings.GOOGLE_CLIENT_ID = "test-client-id.apps.googleusercontent.com"
        settings.GOOGLE_CLIENT_SECRET = "test-secret"
        try:
            resp = await client.post(
                "/api/integrations/gmail/callback",
                json={"code": "code", "state": "attacker-crafted-state"},
                headers=_auth_header(test_user),
            )
            assert resp.status_code == 400
            assert "state mismatch" in resp.json()["detail"].lower()
        finally:
            settings.GOOGLE_CLIENT_ID = ""
            settings.GOOGLE_CLIENT_SECRET = ""

    @pytest.mark.asyncio
    async def test_callback_upserts_on_reconnect(self, client, db_session, test_user):
        """Second callback replaces tokens and clears revoked_at."""
        from src.config import settings
        settings.GOOGLE_CLIENT_ID = "test-client-id.apps.googleusercontent.com"
        settings.GOOGLE_CLIENT_SECRET = "test-secret"

        factory = _make_gmail_stub_factory(
            token_response={
                "access_token": "ya29.new-access",
                "refresh_token": "1//new-refresh",
                "expires_in": 3600,
                "id_token": _make_id_token("user@gmail.com"),
            }
        )
        _override_gmail_http_factory(factory)
        try:
            for _ in range(2):
                state = await _prime_gmail_state(client, _auth_header(test_user))
                resp = await client.post(
                    "/api/integrations/gmail/callback",
                    json={"code": "code", "state": state},
                    headers=_auth_header(test_user),
                )
                assert resp.status_code == 200, resp.text

            result = await db_session.execute(
                select(GmailConnection).where(GmailConnection.user_id == test_user.id)
            )
            rows = list(result.scalars().all())
            assert len(rows) == 1
            assert rows[0].is_active is True
        finally:
            _clear_gmail_http_factory_override()
            settings.GOOGLE_CLIENT_ID = ""
            settings.GOOGLE_CLIENT_SECRET = ""


# =============================================================================
# /status
# =============================================================================


class TestGmailStatus:
    @pytest.mark.asyncio
    async def test_status_connected_after_callback(self, client, db_session, test_user):
        """Status returns connected=True after a successful callback."""
        from src.config import settings
        settings.DEBUG = True
        settings.GOOGLE_CLIENT_ID = "test-client-id.apps.googleusercontent.com"
        settings.GOOGLE_CLIENT_SECRET = "test-secret"

        factory = _make_gmail_stub_factory(
            token_response={
                "access_token": "ya29.tok",
                "refresh_token": "1//ref",
                "expires_in": 3600,
                "id_token": _make_id_token("connected@gmail.com"),
            }
        )
        _override_gmail_http_factory(factory)
        try:
            state = await _prime_gmail_state(client, _auth_header(test_user))
            await client.post(
                "/api/integrations/gmail/callback",
                json={"code": "c", "state": state},
                headers=_auth_header(test_user),
            )

            resp = await client.get("/api/integrations/gmail/status", headers=_auth_header(test_user))
            assert resp.status_code == 200
            body = resp.json()
            assert body["connected"] is True
            assert body["email"] == "connected@gmail.com"
        finally:
            _clear_gmail_http_factory_override()
            settings.GOOGLE_CLIENT_ID = ""
            settings.GOOGLE_CLIENT_SECRET = ""

    @pytest.mark.asyncio
    async def test_status_disconnected_for_new_user(self, client, test_user):
        """Status returns connected=False when no connection exists."""
        resp = await client.get("/api/integrations/gmail/status", headers=_auth_header(test_user))
        assert resp.status_code == 200
        assert resp.json()["connected"] is False


# =============================================================================
# /disconnect
# =============================================================================


class TestGmailDisconnect:
    @pytest.mark.asyncio
    async def test_disconnect_posts_to_revoke_and_sets_revoked_at(
        self, client, db_session, test_user
    ):
        """Disconnect POSTs to Google revoke endpoint and sets revoked_at on the row."""
        from src.config import settings
        settings.DEBUG = True
        settings.GOOGLE_CLIENT_ID = "test-client-id.apps.googleusercontent.com"
        settings.GOOGLE_CLIENT_SECRET = "test-secret"

        captured: dict = {}
        factory = _make_gmail_stub_factory(
            token_response={
                "access_token": "ya29.to-revoke",
                "refresh_token": "1//to-revoke",
                "expires_in": 3600,
                "id_token": _make_id_token("revoke@gmail.com"),
            },
            captured=captured,
        )
        _override_gmail_http_factory(factory)
        try:
            state = await _prime_gmail_state(client, _auth_header(test_user))
            await client.post(
                "/api/integrations/gmail/callback",
                json={"code": "c", "state": state},
                headers=_auth_header(test_user),
            )

            resp = await client.post("/api/integrations/gmail/disconnect", headers=_auth_header(test_user))
            assert resp.status_code == 200
            assert resp.json()["disconnected"] is True

            # Revoke endpoint was called
            assert "revoke_url" in captured
            assert "oauth2.googleapis.com/revoke" in captured["revoke_url"]

            # Row still exists but marked revoked
            db_session.expire_all()
            result = await db_session.execute(
                select(GmailConnection).where(GmailConnection.user_id == test_user.id)
            )
            conn = result.scalar_one()
            assert conn.revoked_at is not None
            assert conn.access_token == ""
            assert conn.refresh_token is None
        finally:
            _clear_gmail_http_factory_override()
            settings.GOOGLE_CLIENT_ID = ""
            settings.GOOGLE_CLIENT_SECRET = ""

    @pytest.mark.asyncio
    async def test_status_disconnected_after_disconnect(self, client, db_session, test_user):
        """Status returns connected=False after disconnect."""
        from src.config import settings
        settings.DEBUG = True
        settings.GOOGLE_CLIENT_ID = "test-client-id.apps.googleusercontent.com"
        settings.GOOGLE_CLIENT_SECRET = "test-secret"

        factory = _make_gmail_stub_factory(
            token_response={
                "access_token": "ya29.tok",
                "refresh_token": "1//ref",
                "expires_in": 3600,
                "id_token": _make_id_token("d@gmail.com"),
            }
        )
        _override_gmail_http_factory(factory)
        try:
            state = await _prime_gmail_state(client, _auth_header(test_user))
            await client.post(
                "/api/integrations/gmail/callback",
                json={"code": "c", "state": state},
                headers=_auth_header(test_user),
            )
            await client.post("/api/integrations/gmail/disconnect", headers=_auth_header(test_user))

            resp = await client.get("/api/integrations/gmail/status", headers=_auth_header(test_user))
            assert resp.status_code == 200
            assert resp.json()["connected"] is False
        finally:
            _clear_gmail_http_factory_override()
            settings.GOOGLE_CLIENT_ID = ""
            settings.GOOGLE_CLIENT_SECRET = ""


# =============================================================================
# /sync (manual-trigger)
# =============================================================================


class TestGmailSyncEndpoint:
    @pytest.mark.asyncio
    async def test_sync_returns_404_when_not_connected(self, client, test_user):
        """POST /sync on a user with no Gmail connection returns 404."""
        resp = await client.post(
            "/api/integrations/gmail/sync", headers=_auth_header(test_user)
        )
        assert resp.status_code == 404
        assert "no active gmail connection" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_sync_returns_429_within_cooldown(
        self, client, db_session, test_user
    ):
        """POST /sync is rate-limited when last_synced_at is within the cooldown.

        Protects Gmail API quota and prevents a user from racing the scheduler
        by spamming the button.
        """
        from datetime import datetime, timezone

        conn = GmailConnection(
            user_id=test_user.id,
            email="user@gmail.com",
            access_token="ya29.test",
            refresh_token="1//test",
            token_expiry=datetime(2099, 1, 1, tzinfo=timezone.utc),
            scopes="openid email profile gmail.send gmail.readonly",
        )
        db_session.add(conn)
        state = GmailSyncState(
            user_id=test_user.id,
            last_history_id="100",
            last_synced_at=datetime.now(timezone.utc),
            failure_count=0,
        )
        db_session.add(state)
        await db_session.commit()

        resp = await client.post(
            "/api/integrations/gmail/sync", headers=_auth_header(test_user)
        )
        assert resp.status_code == 429
        assert "wait" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_sync_returns_404_after_disconnect(
        self, client, db_session, test_user
    ):
        """POST /sync after disconnect (revoked_at set) returns 404."""
        from src.config import settings
        settings.DEBUG = True
        settings.GOOGLE_CLIENT_ID = "test-client-id.apps.googleusercontent.com"
        settings.GOOGLE_CLIENT_SECRET = "test-secret"

        factory = _make_gmail_stub_factory(
            token_response={
                "access_token": "ya29.tok",
                "refresh_token": "1//ref",
                "expires_in": 3600,
                "id_token": _make_id_token("d@gmail.com"),
            }
        )
        _override_gmail_http_factory(factory)
        try:
            state = await _prime_gmail_state(client, _auth_header(test_user))
            await client.post(
                "/api/integrations/gmail/callback",
                json={"code": "c", "state": state},
                headers=_auth_header(test_user),
            )
            await client.post(
                "/api/integrations/gmail/disconnect", headers=_auth_header(test_user)
            )

            resp = await client.post(
                "/api/integrations/gmail/sync", headers=_auth_header(test_user)
            )
            assert resp.status_code == 404
        finally:
            _clear_gmail_http_factory_override()
            settings.GOOGLE_CLIENT_ID = ""
            settings.GOOGLE_CLIENT_SECRET = ""
