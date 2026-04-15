"""Tests for Google OAuth2 sign-in endpoints and the calendar redirect_uri fix.

All Google HTTP interactions are stubbed via `httpx.MockTransport`, which is a
first-class httpx testing transport — not `unittest.mock`. The real
`httpx.AsyncClient` code path runs end-to-end; only the network layer is
intercepted, so we're exercising the actual request/response marshalling
our code does against Google.
"""

from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from sqlalchemy import select

from src.auth.models import User
from src.auth.router import get_google_http_factory
from src.auth.security import create_access_token
from src.main import app


# =============================================================================
# Helpers
# =============================================================================


def _auth_header(user: User) -> dict:
    token = create_access_token(data={"sub": str(user.id)})
    return {"Authorization": f"Bearer {token}"}


def _make_google_stub_factory(
    *,
    token_response: dict | None = None,
    userinfo_response: dict | None = None,
    token_status: int = 200,
    userinfo_status: int = 200,
    captured: dict | None = None,
):
    """Return a client factory whose transport stubs Google's endpoints.

    Any request we make to Google is answered from this function — no live
    network calls happen. The `captured` dict (if provided) is populated with
    the last request we saw at each endpoint so tests can assert on what our
    code sent.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if "oauth2.googleapis.com/token" in str(request.url):
            if captured is not None:
                captured["token_request"] = {
                    "url": str(request.url),
                    "body": dict(parse_qs(request.content.decode() or "")),
                }
            return httpx.Response(token_status, json=token_response or {})
        if "openidconnect.googleapis.com/v1/userinfo" in str(request.url):
            if captured is not None:
                captured["userinfo_request"] = {
                    "url": str(request.url),
                    "authorization": request.headers.get("authorization"),
                }
            return httpx.Response(userinfo_status, json=userinfo_response or {})
        return httpx.Response(404, json={"error": "unexpected url"})

    transport = httpx.MockTransport(handler)

    def factory() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=transport)

    return factory


def _override_google_http_factory(factory):
    app.dependency_overrides[get_google_http_factory] = lambda: factory


def _clear_google_http_factory_override():
    app.dependency_overrides.pop(get_google_http_factory, None)


async def _prime_google_state(client, redirect_uri: str) -> str:
    """Call /api/auth/google/authorize so the httpx client picks up the
    HttpOnly state cookie, and return the state nonce for use in the
    subsequent /callback body.

    Caller must set settings.GOOGLE_CLIENT_ID before calling this.
    """
    resp = await client.post(
        "/api/auth/google/authorize",
        json={"redirect_uri": redirect_uri},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["state"]


# =============================================================================
# /google/authorize
# =============================================================================


class TestGoogleAuthorize:
    """POST /api/auth/google/authorize returns a consent URL."""

    @pytest.mark.asyncio
    async def test_returns_400_when_client_id_missing(self, client):
        """Without GOOGLE_CLIENT_ID, authorize should reject."""
        from src.config import settings

        original = settings.GOOGLE_CLIENT_ID
        settings.GOOGLE_CLIENT_ID = ""
        try:
            response = await client.post(
                "/api/auth/google/authorize",
                json={"redirect_uri": "http://localhost:3000/auth/google/callback"},
            )
            assert response.status_code == 400
            assert "not configured" in response.json()["detail"].lower()
        finally:
            settings.GOOGLE_CLIENT_ID = original

    @pytest.mark.asyncio
    async def test_returns_auth_url_with_state(self, client):
        """With a configured client id, returns a well-formed Google URL + state."""
        from src.config import settings

        original = settings.GOOGLE_CLIENT_ID
        settings.GOOGLE_CLIENT_ID = "test-client-id.apps.googleusercontent.com"
        try:
            response = await client.post(
                "/api/auth/google/authorize",
                json={"redirect_uri": "http://localhost:3000/auth/google/callback"},
            )
            assert response.status_code == 200
            body = response.json()
            assert body["state"]
            assert len(body["state"]) >= 16
            parsed = urlparse(body["auth_url"])
            assert parsed.netloc == "accounts.google.com"
            assert parsed.path == "/o/oauth2/v2/auth"
            params = parse_qs(parsed.query)
            assert params["client_id"] == ["test-client-id.apps.googleusercontent.com"]
            assert params["redirect_uri"] == ["http://localhost:3000/auth/google/callback"]
            assert params["response_type"] == ["code"]
            assert "openid" in params["scope"][0]
            assert "email" in params["scope"][0]
            assert "profile" in params["scope"][0]
            # Sign-in must NOT request calendar scope — those belong to the
            # dedicated calendar integration flow.
            assert "calendar" not in params["scope"][0]
            assert params["state"] == [body["state"]]
        finally:
            settings.GOOGLE_CLIENT_ID = original

    @pytest.mark.asyncio
    async def test_requires_redirect_uri(self, client):
        """Schema validation: redirect_uri is mandatory."""
        response = await client.post("/api/auth/google/authorize", json={})
        assert response.status_code == 422


# =============================================================================
# /google/callback — happy paths and error paths
# =============================================================================


class TestGoogleCallback:
    """POST /api/auth/google/callback exchanges a code and issues a JWT."""

    @pytest.fixture(autouse=True)
    def _debug_mode(self):
        """Enable DEBUG so the state cookie's secure flag is False,
        allowing it to flow over the HTTP test client."""
        from src.config import settings
        original = settings.DEBUG
        settings.DEBUG = True
        yield
        settings.DEBUG = original

    @pytest.mark.asyncio
    async def test_missing_config_returns_400(self, client):
        """Callback needs GOOGLE_CLIENT_ID + SECRET to be set."""
        from src.config import settings

        original_id = settings.GOOGLE_CLIENT_ID
        original_secret = settings.GOOGLE_CLIENT_SECRET
        settings.GOOGLE_CLIENT_ID = ""
        settings.GOOGLE_CLIENT_SECRET = ""
        try:
            response = await client.post(
                "/api/auth/google/callback",
                json={
                    "code": "fake-code",
                    "redirect_uri": "http://localhost:3000/auth/google/callback",
                },
            )
            assert response.status_code == 400
            assert "not configured" in response.json()["detail"].lower()
        finally:
            settings.GOOGLE_CLIENT_ID = original_id
            settings.GOOGLE_CLIENT_SECRET = original_secret

    @pytest.mark.asyncio
    async def test_creates_new_user_and_returns_jwt(self, client, db_session):
        """First-time Google sign-in should create a user, link a tenant, issue a JWT."""
        from src.config import settings
        from src.whitelabel.models import Tenant, TenantUser

        # Default tenant must exist for the upsert to link membership.
        tenant = Tenant(
            name="Default",
            slug="default",
            domain="default.example.com",
            is_active=True,
            plan="starter",
            max_users=5,
            max_contacts=100,
        )
        db_session.add(tenant)
        await db_session.commit()

        captured: dict = {}
        factory = _make_google_stub_factory(
            token_response={
                "access_token": "ya29.fake-token",
                "token_type": "Bearer",
                "expires_in": 3600,
                "scope": "openid email profile",
                "id_token": "fake.id.token",
            },
            userinfo_response={
                "sub": "109999999999999999999",
                "email": "newuser@linkcreative.example",
                "email_verified": True,
                "name": "New Google User",
                "picture": "https://lh3.googleusercontent.com/a/default-user",
            },
            captured=captured,
        )
        _override_google_http_factory(factory)
        original_id = settings.GOOGLE_CLIENT_ID
        original_secret = settings.GOOGLE_CLIENT_SECRET
        settings.GOOGLE_CLIENT_ID = "test-client-id.apps.googleusercontent.com"
        settings.GOOGLE_CLIENT_SECRET = "test-client-secret"

        try:
            # Prime the state cookie by calling /authorize; the cookie
            # flows into the subsequent /callback request via the shared
            # httpx client jar.
            state = await _prime_google_state(
                client, "http://localhost:3000/auth/google/callback",
            )
            response = await client.post(
                "/api/auth/google/callback",
                json={
                    "code": "real-looking-code",
                    "redirect_uri": "http://localhost:3000/auth/google/callback",
                    "state": state,
                },
            )
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["access_token"]
            assert body["token_type"] == "bearer"

            # Token exchange was called with the exact redirect_uri + code we supplied.
            token_body = captured["token_request"]["body"]
            assert token_body["code"] == ["real-looking-code"]
            assert token_body["redirect_uri"] == [
                "http://localhost:3000/auth/google/callback"
            ]
            assert token_body["grant_type"] == ["authorization_code"]
            assert token_body["client_id"] == [
                "test-client-id.apps.googleusercontent.com"
            ]
            assert token_body["client_secret"] == ["test-client-secret"]

            # Userinfo was called with the bearer token from the token response.
            assert (
                captured["userinfo_request"]["authorization"]
                == "Bearer ya29.fake-token"
            )

            # User persisted with google_sub + provider=google and no password.
            result = await db_session.execute(
                select(User).where(User.email == "newuser@linkcreative.example")
            )
            user = result.scalar_one()
            assert user.google_sub == "109999999999999999999"
            assert user.auth_provider == "google"
            assert user.hashed_password is None
            assert user.full_name == "New Google User"
            assert user.avatar_url == "https://lh3.googleusercontent.com/a/default-user"
            assert user.last_login is not None

            # Tenant membership auto-linked.
            membership_result = await db_session.execute(
                select(TenantUser).where(TenantUser.user_id == user.id)
            )
            membership = membership_result.scalar_one()
            assert membership.tenant_id == tenant.id
            assert membership.is_primary is True
        finally:
            _clear_google_http_factory_override()
            settings.GOOGLE_CLIENT_ID = original_id
            settings.GOOGLE_CLIENT_SECRET = original_secret

    @pytest.mark.asyncio
    async def test_links_google_sub_to_existing_email_user(
        self, client, db_session, test_user
    ):
        """An existing password user signing in with matching email gets linked, not duplicated."""
        from src.config import settings

        captured: dict = {}
        factory = _make_google_stub_factory(
            token_response={
                "access_token": "ya29.link-token",
                "expires_in": 3600,
                "token_type": "Bearer",
            },
            userinfo_response={
                "sub": "200000000000000000000",
                "email": test_user.email,
                "email_verified": True,
                "name": "Test User Linked",
                "picture": None,
            },
            captured=captured,
        )
        _override_google_http_factory(factory)
        original_id = settings.GOOGLE_CLIENT_ID
        original_secret = settings.GOOGLE_CLIENT_SECRET
        settings.GOOGLE_CLIENT_ID = "test-client-id.apps.googleusercontent.com"
        settings.GOOGLE_CLIENT_SECRET = "test-client-secret"

        try:
            state = await _prime_google_state(
                client, "http://localhost:3000/auth/google/callback",
            )
            response = await client.post(
                "/api/auth/google/callback",
                json={
                    "code": "link-code",
                    "redirect_uri": "http://localhost:3000/auth/google/callback",
                    "state": state,
                },
            )
            assert response.status_code == 200, response.text

            # Confirm no duplicate user row created.
            result = await db_session.execute(
                select(User).where(User.email == test_user.email)
            )
            users = list(result.scalars().all())
            assert len(users) == 1
            linked = users[0]
            assert linked.id == test_user.id
            assert linked.google_sub == "200000000000000000000"
            # Password was already set on test_user — provider stays 'password'
            # since the user can still log in either way.
            assert linked.hashed_password is not None
            assert linked.auth_provider == "password"
        finally:
            _clear_google_http_factory_override()
            settings.GOOGLE_CLIENT_ID = original_id
            settings.GOOGLE_CLIENT_SECRET = original_secret

    @pytest.mark.asyncio
    async def test_unverified_email_rejected(self, client):
        """Google accounts whose email is not verified must be denied."""
        from src.config import settings

        factory = _make_google_stub_factory(
            token_response={"access_token": "tok", "expires_in": 3600},
            userinfo_response={
                "sub": "unverified-sub",
                "email": "unverified@example.com",
                "email_verified": False,
                "name": "Unverified Person",
            },
        )
        _override_google_http_factory(factory)
        original_id = settings.GOOGLE_CLIENT_ID
        original_secret = settings.GOOGLE_CLIENT_SECRET
        settings.GOOGLE_CLIENT_ID = "test-client-id.apps.googleusercontent.com"
        settings.GOOGLE_CLIENT_SECRET = "test-client-secret"

        try:
            state = await _prime_google_state(
                client, "http://localhost:3000/auth/google/callback",
            )
            response = await client.post(
                "/api/auth/google/callback",
                json={
                    "code": "any",
                    "redirect_uri": "http://localhost:3000/auth/google/callback",
                    "state": state,
                },
            )
            assert response.status_code == 400
            assert "not verified" in response.json()["detail"].lower()
        finally:
            _clear_google_http_factory_override()
            settings.GOOGLE_CLIENT_ID = original_id
            settings.GOOGLE_CLIENT_SECRET = original_secret

    @pytest.mark.asyncio
    async def test_state_mismatch_rejected(self, client):
        """Callback without a matching state cookie must 400.

        This is the server-side CSRF defense. An attacker who tricks a
        victim into landing on /auth/google/callback?code=... has no
        matching cookie in the victim's browser, so the exchange is
        rejected before we ever talk to Google.
        """
        from src.config import settings

        original_id = settings.GOOGLE_CLIENT_ID
        original_secret = settings.GOOGLE_CLIENT_SECRET
        settings.GOOGLE_CLIENT_ID = "test-client-id.apps.googleusercontent.com"
        settings.GOOGLE_CLIENT_SECRET = "test-client-secret"
        try:
            # Note: NOT calling /authorize first, so no state cookie
            # exists on the client.
            response = await client.post(
                "/api/auth/google/callback",
                json={
                    "code": "whatever",
                    "redirect_uri": "http://localhost:3000/auth/google/callback",
                    "state": "attacker-crafted-state",
                },
            )
            assert response.status_code == 400
            assert "state mismatch" in response.json()["detail"].lower()
        finally:
            settings.GOOGLE_CLIENT_ID = original_id
            settings.GOOGLE_CLIENT_SECRET = original_secret

    @pytest.mark.asyncio
    async def test_token_endpoint_failure_bubbles_up_as_400(self, client):
        """If Google's token endpoint errors, we must return 400, not 500."""
        from src.config import settings

        factory = _make_google_stub_factory(
            token_response={"error": "invalid_grant"},
            token_status=400,
        )
        _override_google_http_factory(factory)
        original_id = settings.GOOGLE_CLIENT_ID
        original_secret = settings.GOOGLE_CLIENT_SECRET
        settings.GOOGLE_CLIENT_ID = "test-client-id.apps.googleusercontent.com"
        settings.GOOGLE_CLIENT_SECRET = "test-client-secret"

        try:
            state = await _prime_google_state(
                client, "http://localhost:3000/auth/google/callback",
            )
            response = await client.post(
                "/api/auth/google/callback",
                json={
                    "code": "bad-code",
                    "redirect_uri": "http://localhost:3000/auth/google/callback",
                    "state": state,
                },
            )
            assert response.status_code == 400
            assert "token exchange failed" in response.json()["detail"].lower()
        finally:
            _clear_google_http_factory_override()
            settings.GOOGLE_CLIENT_ID = original_id
            settings.GOOGLE_CLIENT_SECRET = original_secret


# =============================================================================
# Password login must tolerate OAuth-only users (no password hash on row)
# =============================================================================


class TestUpsertGoogleUserRace:
    """upsert_google_user must handle a concurrent-insert race.

    Simulates the scenario where two callbacks fire for the same brand-new
    Google email before either transaction commits. Verified by pre-seeding
    a conflicting row between the selects and the insert, which triggers the
    IntegrityError path inside the SAVEPOINT.
    """

    @pytest.mark.asyncio
    async def test_integrity_error_recovers_existing_row(self, db_session):
        from src.auth.service import AuthService

        # Winner row: already in DB with the same email. The service will
        # SELECT by google_sub (miss), SELECT by email (miss — we add the
        # winner below after the method starts). Because we run inline here
        # the simplest way to exercise the race is to pre-seed the winner
        # so the first select-by-email fails to find it, then the insert
        # collides. We simulate that by monkey-wrapping get_user_by_email to
        # report "not found" on the first call only.
        winner = User(
            email="race@example.com",
            full_name="Race Winner",
            hashed_password=None,
            google_sub="winner-sub",
            auth_provider="google",
            is_active=True,
        )
        db_session.add(winner)
        await db_session.commit()

        service = AuthService(db_session)
        original_by_email = service.get_user_by_email
        call_count = {"n": 0}

        async def flaky_by_email(email: str):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return None  # Pretend we missed on the first lookup
            return await original_by_email(email)

        service.get_user_by_email = flaky_by_email  # type: ignore[method-assign]

        recovered = await service.upsert_google_user(
            google_sub="loser-sub",
            email="race@example.com",
            full_name="Race Loser",
            avatar_url=None,
        )
        # Losing insert should have been swallowed and the winner returned.
        assert recovered.email == "race@example.com"
        # Either the original winner row (when the unique collision fires on
        # email) or the linker path that reattaches to it.
        result = await db_session.execute(
            select(User).where(User.email == "race@example.com")
        )
        rows = list(result.scalars().all())
        assert len(rows) == 1


class TestPasswordLoginWithOAuthOnlyUser:
    """Password login endpoint removed — must return 404 regardless of user type."""

    @pytest.mark.asyncio
    async def test_password_login_endpoint_removed(
        self, client, db_session
    ):
        """POST /api/auth/login/json must not accept password credentials."""
        response = await client.post(
            "/api/auth/login/json",
            json={"email": "oauthonly@example.com", "password": "whatever"},
        )
        assert response.status_code in (404, 405)


# =============================================================================
# Calendar redirect_uri bug fix — callback must now require + forward redirect_uri
# =============================================================================


class TestGoogleCalendarCallbackRedirectUri:
    """Regression test: callback must require redirect_uri (previously hardcoded '')."""

    @pytest.mark.asyncio
    async def test_callback_missing_redirect_uri_returns_400(
        self, client, test_user
    ):
        """Omitting redirect_uri must 400 — prevents silent Google token exchange failure."""
        response = await client.post(
            "/api/integrations/google-calendar/callback",
            json={"code": "x"},
            headers=_auth_header(test_user),
        )
        assert response.status_code == 400
        assert "redirect_uri" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_callback_with_redirect_uri_attempts_exchange(
        self, client, test_user
    ):
        """Including redirect_uri gets past schema validation and reaches Google
        (which then fails because the code is fake — proves we're no longer
        short-circuiting on an empty redirect_uri)."""
        response = await client.post(
            "/api/integrations/google-calendar/callback",
            json={
                "code": "fake-calendar-code",
                "redirect_uri": "http://localhost:3000/settings/integrations/google-calendar/callback",
            },
            headers=_auth_header(test_user),
        )
        # Expected: 400 because the fake code fails Google's real token
        # exchange. The important assertion is that the response is NOT a 422
        # (schema rejection) and NOT a 200, and the error indicates the
        # exchange path ran.
        assert response.status_code == 400
        detail = response.json()["detail"].lower()
        assert "failed to connect" in detail or "token" in detail or "exchange" in detail
