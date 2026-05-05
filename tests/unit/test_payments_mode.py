"""Tests for GET /api/payments/mode endpoint.

Covers unconfigured, test-key, live-key, and unauthorized access.
Stubs settings.STRIPE_SECRET_KEY + STRIPE_PUBLISHABLE_KEY at the Stripe SDK boundary.
"""

import pytest
from httpx import AsyncClient

from src.auth.security import get_password_hash, create_access_token
from src.auth.models import User


def _token(user: User) -> dict:
    token = create_access_token(data={"sub": str(user.id)})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def plain_user(db_session):
    user = User(
        email="mode_test_user@test.com",
        hashed_password=get_password_hash("password123"),
        full_name="Mode Test User",
        is_active=True,
        is_superuser=False,
        role="sales_rep",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_stripe_mode_unconfigured(client: AsyncClient, plain_user: User, monkeypatch):
    """Returns mode='unconfigured' when STRIPE_SECRET_KEY is empty."""
    import src.config as cfg
    monkeypatch.setattr(cfg.settings, "STRIPE_SECRET_KEY", "")
    monkeypatch.setattr(cfg.settings, "STRIPE_PUBLISHABLE_KEY", "")

    resp = await client.get("/api/payments/mode", headers=_token(plain_user))
    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "unconfigured"
    assert data["publishable_hint"] is None


@pytest.mark.asyncio
async def test_stripe_mode_test_key(client: AsyncClient, plain_user: User, monkeypatch):
    """Returns mode='test' and publishable_hint when STRIPE_SECRET_KEY starts with sk_test_."""
    import src.config as cfg
    monkeypatch.setattr(cfg.settings, "STRIPE_SECRET_KEY", "sk_test_abc123")
    monkeypatch.setattr(cfg.settings, "STRIPE_PUBLISHABLE_KEY", "pk_test_xyz")

    resp = await client.get("/api/payments/mode", headers=_token(plain_user))
    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "test"
    # `publishable_hint` is the env-prefix only, not the full key.
    assert data["publishable_hint"] == "pk_test_"


@pytest.mark.asyncio
async def test_stripe_mode_live_key(client: AsyncClient, plain_user: User, monkeypatch):
    """Returns mode='live' when STRIPE_SECRET_KEY starts with sk_live_."""
    import src.config as cfg
    monkeypatch.setattr(cfg.settings, "STRIPE_SECRET_KEY", "sk_live_def456")
    monkeypatch.setattr(cfg.settings, "STRIPE_PUBLISHABLE_KEY", "pk_live_abc")

    resp = await client.get("/api/payments/mode", headers=_token(plain_user))
    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "live"
    assert data["publishable_hint"] == "pk_live_"


@pytest.mark.asyncio
async def test_stripe_mode_unauthorized(client: AsyncClient):
    """Returns 401 when no auth token is provided."""
    resp = await client.get("/api/payments/mode")
    assert resp.status_code == 401
