"""Gmail OAuth2 helpers — thin wrappers around Google token + id_token decode.

Injectable HttpClientFactory keeps Google HTTP calls out of tests.
"""

import base64
import json
import os
from typing import Callable
from urllib.parse import urlencode

import httpx

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"

GMAIL_SCOPES = (
    "openid email profile "
    "https://www.googleapis.com/auth/gmail.send "
    "https://www.googleapis.com/auth/gmail.readonly"
)

# Canonical ordered scope list stored on GmailConnection.scopes
CANONICAL_SCOPES = "openid email profile gmail.send gmail.readonly"

HttpClientFactory = Callable[[], httpx.AsyncClient]


def default_client_factory() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=10.0)


def get_redirect_uri() -> str:
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
    return f"{frontend_url}/settings/integrations/gmail/callback"


def build_authorize_url(client_id: str, redirect_uri: str, state: str, login_hint: str = "") -> str:
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": GMAIL_SCOPES,
        "access_type": "offline",
        "prompt": "consent select_account",
        "state": state,
    }
    if login_hint:
        params["login_hint"] = login_hint
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


def decode_id_token_email(id_token: str) -> str | None:
    """Extract email from JWT id_token without signature verification.

    Signature verification is Google's job — we've already exchanged a code
    directly with Google's token endpoint over TLS, so we trust the payload.
    """
    try:
        parts = id_token.split(".")
        if len(parts) < 2:
            return None
        payload_b64 = parts[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        return payload.get("email")
    except Exception:
        return None


async def exchange_code_for_tokens(
    *,
    code: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    client_factory: HttpClientFactory = default_client_factory,
) -> dict:
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


async def revoke_token(
    token: str,
    client_factory: HttpClientFactory = default_client_factory,
) -> None:
    async with client_factory() as client:
        await client.post(GOOGLE_REVOKE_URL, params={"token": token})
