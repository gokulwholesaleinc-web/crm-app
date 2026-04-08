"""Google OAuth2 helpers for the sign-in flow.

Thin wrappers around Google's token + userinfo endpoints. Kept free of
SQLAlchemy/FastAPI concerns so the auth service can call them directly and
tests can inject a custom httpx transport without mocks.
"""

from typing import Callable, Optional
from urllib.parse import urlencode

import httpx

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"

# OpenID + email + profile is the minimum needed for sign-in.
# We intentionally do NOT request calendar scopes here — the calendar
# integration has its own OAuth flow so users can grant one without the other.
SIGN_IN_SCOPES = "openid email profile"


# Tests inject a custom AsyncClient factory to stub Google without mocking.
HttpClientFactory = Callable[[], httpx.AsyncClient]


def default_client_factory() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=10.0)


def build_authorize_url(
    client_id: str,
    redirect_uri: str,
    state: Optional[str] = None,
) -> str:
    """Build the Google consent URL for sign-in.

    `state` should be a server-generated nonce the caller can verify on the
    callback to defend against CSRF on the token exchange.
    """
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": SIGN_IN_SCOPES,
        "access_type": "online",
        "include_granted_scopes": "true",
        "prompt": "select_account",
    }
    if state:
        params["state"] = state
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


async def exchange_code_for_tokens(
    *,
    code: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    client_factory: HttpClientFactory = default_client_factory,
) -> dict:
    """Exchange an authorization code for Google tokens.

    Returns the raw JSON body from Google (contains access_token, id_token,
    expires_in, scope, token_type).
    """
    async with client_factory() as client:
        response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        response.raise_for_status()
        return response.json()


async def fetch_userinfo(
    *,
    access_token: str,
    client_factory: HttpClientFactory = default_client_factory,
) -> dict:
    """Call the OIDC userinfo endpoint and return the profile dict.

    Keys of interest: `sub` (stable Google user id), `email`,
    `email_verified`, `name`, `picture`.
    """
    async with client_factory() as client:
        response = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        response.raise_for_status()
        return response.json()
