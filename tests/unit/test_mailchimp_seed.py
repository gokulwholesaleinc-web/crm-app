"""Tests for the boot-time Mailchimp env-var seed.

The seed reads ``MAILCHIMP_API_KEY`` (and optional
``MAILCHIMP_DEFAULT_AUDIENCE_ID``) and creates a MailchimpConnection
for each active tenant that doesn't already have one. UI-set
connections are never overwritten.
"""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.integrations.mailchimp.client import MailchimpClient
from src.integrations.mailchimp.models import MailchimpConnection
from src.integrations.mailchimp.seed import seed_mailchimp_from_env
from src.whitelabel.models import Tenant, TenantSettings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_transport(extra: dict[str, dict] | None = None) -> httpx.MockTransport:
    routes = {
        ("GET", "/3.0/ping"): {"health_status": "ok"},
        ("GET", "/3.0/"): {"account_id": "acct-1", "email": "ops@example.com"},
    }
    if extra:
        routes.update(extra)

    def handler(request: httpx.Request) -> httpx.Response:
        spec = routes.get((request.method.upper(), request.url.path))
        if spec is None:
            return httpx.Response(599, json={"detail": f"unmocked {request.url.path}"})
        return httpx.Response(200, json=spec)

    return httpx.MockTransport(handler)


def _factory(transport: httpx.MockTransport):
    async def make(api_key: str, server_prefix: str) -> MailchimpClient:
        return MailchimpClient(api_key, server_prefix, transport=transport)

    return make


async def _make_tenant(db: AsyncSession, slug: str) -> Tenant:
    tenant = Tenant(name=slug.title(), slug=slug, is_active=True)
    db.add(tenant)
    await db.flush()
    db.add(TenantSettings(tenant_id=tenant.id))
    await db.commit()
    await db.refresh(tenant)
    return tenant


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSeedMailchimpFromEnv:
    @pytest.mark.asyncio
    async def test_no_op_when_env_unset(self, db_session: AsyncSession, monkeypatch):
        await _make_tenant(db_session, "no-env")
        monkeypatch.setattr(settings, "MAILCHIMP_API_KEY", "")
        seeded = await seed_mailchimp_from_env(db_session)
        assert seeded == 0
        rows = (await db_session.execute(select(MailchimpConnection))).scalars().all()
        assert rows == []

    @pytest.mark.asyncio
    async def test_creates_connection_per_tenant(
        self, db_session: AsyncSession, monkeypatch
    ):
        t1 = await _make_tenant(db_session, "alpha")
        t2 = await _make_tenant(db_session, "beta")
        monkeypatch.setattr(settings, "MAILCHIMP_API_KEY", "abc-us19")
        monkeypatch.setattr(settings, "MAILCHIMP_DEFAULT_AUDIENCE_ID", "")

        transport = _make_transport()
        seeded = await seed_mailchimp_from_env(
            db_session, client_factory=_factory(transport)
        )
        assert seeded == 2

        for t in (t1, t2):
            row = (
                await db_session.execute(
                    select(MailchimpConnection).where(MailchimpConnection.tenant_id == t.id)
                )
            ).scalar_one()
            assert row.api_key == "abc-us19"
            assert row.server_prefix == "us19"
            assert row.account_email == "ops@example.com"
            assert row.default_audience_id is None

    @pytest.mark.asyncio
    async def test_skips_tenant_with_existing_connection(
        self, db_session: AsyncSession, monkeypatch
    ):
        """UI-set connection wins — boot-time seed must not clobber it."""
        tenant = await _make_tenant(db_session, "kept")
        existing = MailchimpConnection(
            tenant_id=tenant.id,
            api_key="ui-set-key-us99",
            server_prefix="us99",
            default_audience_id="audience-from-ui",
        )
        db_session.add(existing)
        await db_session.commit()

        monkeypatch.setattr(settings, "MAILCHIMP_API_KEY", "env-key-us19")
        monkeypatch.setattr(settings, "MAILCHIMP_DEFAULT_AUDIENCE_ID", "")
        # No transport patching needed — the seed should never call out.
        seeded = await seed_mailchimp_from_env(db_session)
        assert seeded == 0

        await db_session.refresh(existing)
        assert existing.api_key == "ui-set-key-us99"
        assert existing.default_audience_id == "audience-from-ui"

    @pytest.mark.asyncio
    async def test_pins_default_audience_when_env_set(
        self, db_session: AsyncSession, monkeypatch
    ):
        tenant = await _make_tenant(db_session, "withaud")
        monkeypatch.setattr(settings, "MAILCHIMP_API_KEY", "abc-us19")
        monkeypatch.setattr(settings, "MAILCHIMP_DEFAULT_AUDIENCE_ID", "list-7")

        transport = _make_transport(
            {("GET", "/3.0/lists/list-7"): {"id": "list-7", "name": "Newsletter"}}
        )
        seeded = await seed_mailchimp_from_env(
            db_session, client_factory=_factory(transport)
        )
        assert seeded == 1
        row = (
            await db_session.execute(
                select(MailchimpConnection).where(MailchimpConnection.tenant_id == tenant.id)
            )
        ).scalar_one()
        assert row.default_audience_id == "list-7"
        assert row.default_audience_name == "Newsletter"

    @pytest.mark.asyncio
    async def test_skips_inactive_tenant(self, db_session: AsyncSession, monkeypatch):
        tenant = Tenant(name="Off", slug="off", is_active=False)
        db_session.add(tenant)
        await db_session.commit()

        monkeypatch.setattr(settings, "MAILCHIMP_API_KEY", "abc-us19")
        # Patching not required — no active tenants means no API call.
        seeded = await seed_mailchimp_from_env(db_session)
        assert seeded == 0
