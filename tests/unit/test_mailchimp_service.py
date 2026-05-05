"""Unit tests for the MailchimpService connect / audience / send flow.

The service runs against the real test database via the ``db_session``
fixture; only the Mailchimp HTTP transport is faked (httpx.MockTransport)
so we don't make outbound network calls. CLAUDE.md prohibits mocking
internal services — the DB, ORM, and CRM models are all real here.
"""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.campaigns.models import Campaign, CampaignMember, EmailTemplate
from src.contacts.models import Contact
from src.integrations.mailchimp.client import MailchimpClient
from src.integrations.mailchimp.models import MailchimpConnection
from src.integrations.mailchimp.service import (
    MailchimpNotConnected,
    MailchimpService,
)
from src.whitelabel.models import Tenant, TenantSettings, TenantUser


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _route(handlers: dict[tuple[str, str], object]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        key = (request.method.upper(), request.url.path)
        spec = handlers.get(key)
        if spec is None:
            return httpx.Response(599, json={"detail": f"unmocked {key}"})
        if isinstance(spec, httpx.Response):
            return spec
        if isinstance(spec, tuple):
            status, body = spec
            return httpx.Response(status, json=body)
        return httpx.Response(200, json=spec)

    return httpx.MockTransport(handler)


def _factory(transport: httpx.MockTransport):
    async def make(api_key: str, server_prefix: str) -> MailchimpClient:
        return MailchimpClient(api_key, server_prefix, transport=transport)

    return make


async def _make_tenant(db: AsyncSession, slug: str = "t1") -> Tenant:
    tenant = Tenant(name="Acme", slug=slug)
    db.add(tenant)
    await db.flush()
    db.add(TenantSettings(tenant_id=tenant.id))
    await db.commit()
    await db.refresh(tenant)
    return tenant


# ---------------------------------------------------------------------------
# connect
# ---------------------------------------------------------------------------


class TestConnect:
    @pytest.mark.asyncio
    async def test_connect_validates_key_and_persists_account(
        self, db_session: AsyncSession, test_user: User
    ):
        tenant = await _make_tenant(db_session)
        transport = _route({
            ("GET", "/3.0/ping"): {"health_status": "Everything's Chimpy!"},
            ("GET", "/3.0/"): {
                "account_id": "acct-1",
                "email": "info@example.com",
            },
        })
        service = MailchimpService(db_session, client_factory=_factory(transport))

        conn = await service.connect(
            tenant_id=tenant.id,
            connected_by_id=test_user.id,
            api_key="abc123-us19",
        )
        await db_session.commit()

        assert conn.tenant_id == tenant.id
        assert conn.server_prefix == "us19"
        assert conn.account_email == "info@example.com"
        assert conn.account_login_id == "acct-1"
        assert conn.connected_by_id == test_user.id
        assert conn.revoked_at is None

    @pytest.mark.asyncio
    async def test_connect_rejects_key_without_dc(
        self, db_session: AsyncSession, test_user: User
    ):
        tenant = await _make_tenant(db_session)
        service = MailchimpService(db_session)
        with pytest.raises(ValueError):
            await service.connect(
                tenant_id=tenant.id,
                connected_by_id=test_user.id,
                api_key="nodatacenter",
            )

    @pytest.mark.asyncio
    async def test_connect_replaces_credentials_on_re_connect(
        self, db_session: AsyncSession, test_user: User
    ):
        tenant = await _make_tenant(db_session, slug="reconn")
        transport = _route({
            ("GET", "/3.0/ping"): {"health_status": "ok"},
            ("GET", "/3.0/"): {"account_id": "acct-1", "email": "v1@example.com"},
        })
        service = MailchimpService(db_session, client_factory=_factory(transport))
        first = await service.connect(
            tenant_id=tenant.id,
            connected_by_id=test_user.id,
            api_key="key1-us10",
        )
        await db_session.commit()

        transport2 = _route({
            ("GET", "/3.0/ping"): {"health_status": "ok"},
            ("GET", "/3.0/"): {"account_id": "acct-2", "email": "v2@example.com"},
        })
        service2 = MailchimpService(db_session, client_factory=_factory(transport2))
        second = await service2.connect(
            tenant_id=tenant.id,
            connected_by_id=test_user.id,
            api_key="key2-us20",
        )
        await db_session.commit()
        assert first.id == second.id
        assert second.api_key == "key2-us20"
        assert second.server_prefix == "us20"
        assert second.account_email == "v2@example.com"


# ---------------------------------------------------------------------------
# audiences + default selection
# ---------------------------------------------------------------------------


class TestAudiences:
    @pytest.mark.asyncio
    async def test_set_default_audience_persists_id_and_name(
        self, db_session: AsyncSession, test_user: User
    ):
        tenant = await _make_tenant(db_session, slug="aud")
        db_session.add(MailchimpConnection(
            tenant_id=tenant.id,
            api_key="key-us19",
            server_prefix="us19",
            connected_by_id=test_user.id,
        ))
        await db_session.commit()

        transport = _route({
            ("GET", "/3.0/lists/list-42"): {"id": "list-42", "name": "VIP"},
        })
        service = MailchimpService(db_session, client_factory=_factory(transport))
        conn = await service.set_default_audience(tenant.id, "list-42")
        assert conn.default_audience_id == "list-42"
        assert conn.default_audience_name == "VIP"

    @pytest.mark.asyncio
    async def test_list_audiences_requires_connection(self, db_session: AsyncSession):
        tenant = await _make_tenant(db_session, slug="empty")
        service = MailchimpService(db_session)
        with pytest.raises(MailchimpNotConnected):
            await service.list_audiences(tenant.id)


# ---------------------------------------------------------------------------
# send_campaign_step
# ---------------------------------------------------------------------------


class TestSendCampaignStep:
    @pytest.mark.asyncio
    async def test_send_campaign_step_pushes_members_and_sends(
        self, db_session: AsyncSession, test_user: User
    ):
        tenant = await _make_tenant(db_session, slug="send")
        db_session.add(TenantUser(
            tenant_id=tenant.id, user_id=test_user.id, is_primary=True,
        ))
        db_session.add(MailchimpConnection(
            tenant_id=tenant.id,
            api_key="key-us19",
            server_prefix="us19",
            default_audience_id="list-1",
            connected_by_id=test_user.id,
            account_email="ops@example.com",
        ))

        contact = Contact(
            first_name="Ada",
            last_name="Lovelace",
            email="ada@example.com",
            owner_id=test_user.id,
        )
        db_session.add(contact)
        await db_session.flush()

        template = EmailTemplate(
            name="welcome",
            subject_template="Hello",
            body_template="<p>Welcome</p>",
            created_by_id=test_user.id,
        )
        db_session.add(template)
        await db_session.flush()

        campaign = Campaign(
            name="Spring",
            campaign_type="email",
            send_via="mailchimp",
            owner_id=test_user.id,
        )
        db_session.add(campaign)
        await db_session.flush()
        db_session.add(CampaignMember(
            campaign_id=campaign.id,
            member_type="contact",
            member_id=contact.id,
        ))
        await db_session.commit()

        seen_paths: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen_paths.append(f"{request.method} {request.url.path}")
            if request.url.path.startswith("/3.0/lists/list-1/members/"):
                return httpx.Response(200, json={"id": "h", "email_address": "ada@example.com"})
            if request.url.path == "/3.0/campaigns" and request.method == "POST":
                return httpx.Response(200, json={"id": "mc-camp-1"})
            if request.url.path == "/3.0/campaigns/mc-camp-1/content":
                return httpx.Response(200, json={"html": "ok"})
            if request.url.path == "/3.0/campaigns/mc-camp-1/actions/send":
                return httpx.Response(204)
            return httpx.Response(599, json={"detail": "unmocked"})

        transport = httpx.MockTransport(handler)
        service = MailchimpService(
            db_session, client_factory=_factory(transport)
        )

        summary = await service.send_campaign_step(
            campaign=campaign,
            template_id=template.id,
            sent_by_id=test_user.id,
            tenant_id=tenant.id,
        )
        await db_session.commit()

        assert summary["mailchimp_campaign_id"] == "mc-camp-1"
        assert summary["emails_sent"] == 1
        assert campaign.mailchimp_campaign_id == "mc-camp-1"
        assert campaign.num_sent == 1
        # Verify the right Mailchimp endpoints were hit in order.
        assert any("PUT /3.0/lists/list-1/members/" in p for p in seen_paths)
        assert "POST /3.0/campaigns" in seen_paths
        assert "PUT /3.0/campaigns/mc-camp-1/content" in seen_paths
        assert "POST /3.0/campaigns/mc-camp-1/actions/send" in seen_paths

    @pytest.mark.asyncio
    async def test_send_campaign_step_short_circuits_when_already_sent(
        self, db_session: AsyncSession, test_user: User
    ):
        """If a prior tick already kicked off the Mailchimp send, the
        re-entry must NOT re-fire create+send — re-sending a Mailchimp
        regular campaign would mail the entire audience a second time.
        """
        tenant = await _make_tenant(db_session, slug="idem")
        db_session.add(TenantUser(
            tenant_id=tenant.id, user_id=test_user.id, is_primary=True,
        ))
        db_session.add(MailchimpConnection(
            tenant_id=tenant.id,
            api_key="key-us19",
            server_prefix="us19",
            default_audience_id="list-1",
            connected_by_id=test_user.id,
        ))
        template = EmailTemplate(
            name="x", subject_template="S", body_template="B"
        )
        db_session.add(template)
        await db_session.flush()
        campaign = Campaign(
            name="Replay",
            campaign_type="email",
            send_via="mailchimp",
            owner_id=test_user.id,
            mailchimp_campaign_id="already-fired",
        )
        db_session.add(campaign)
        await db_session.commit()

        def handler(request: httpx.Request) -> httpx.Response:
            raise AssertionError(
                f"transport hit unexpectedly: {request.method} {request.url.path}"
            )

        transport = httpx.MockTransport(handler)
        service = MailchimpService(
            db_session, client_factory=_factory(transport)
        )
        summary = await service.send_campaign_step(
            campaign=campaign,
            template_id=template.id,
            sent_by_id=test_user.id,
            tenant_id=tenant.id,
        )
        assert summary["skipped"] == "already_sent"
        assert summary["emails_sent"] == 0
        assert summary["mailchimp_campaign_id"] == "already-fired"

    @pytest.mark.asyncio
    async def test_send_campaign_step_reraises_auth_errors_during_upsert(
        self, db_session: AsyncSession, test_user: User
    ):
        """A 401 on member upsert means the API key is invalid — we must
        NOT then proceed to create+send, which would mail a stale
        audience snapshot. Compliance-state 400s remain skipped."""
        from src.integrations.mailchimp.client import MailchimpError

        tenant = await _make_tenant(db_session, slug="autherr")
        db_session.add(TenantUser(
            tenant_id=tenant.id, user_id=test_user.id, is_primary=True,
        ))
        db_session.add(MailchimpConnection(
            tenant_id=tenant.id,
            api_key="key-us19",
            server_prefix="us19",
            default_audience_id="list-1",
            connected_by_id=test_user.id,
        ))
        contact = Contact(
            first_name="A", last_name="B", email="ab@example.com",
            owner_id=test_user.id,
        )
        db_session.add(contact)
        template = EmailTemplate(
            name="x", subject_template="S", body_template="B"
        )
        db_session.add(template)
        await db_session.flush()
        campaign = Campaign(
            name="C", campaign_type="email",
            send_via="mailchimp", owner_id=test_user.id,
        )
        db_session.add(campaign)
        await db_session.flush()
        db_session.add(CampaignMember(
            campaign_id=campaign.id, member_type="contact", member_id=contact.id,
        ))
        await db_session.commit()

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.startswith("/3.0/lists/list-1/members/"):
                return httpx.Response(401, json={"detail": "API key not found"})
            raise AssertionError(
                f"send was attempted after auth failure: {request.url.path}"
            )

        transport = httpx.MockTransport(handler)
        service = MailchimpService(db_session, client_factory=_factory(transport))
        with pytest.raises(MailchimpError):
            await service.send_campaign_step(
                campaign=campaign,
                template_id=template.id,
                sent_by_id=test_user.id,
                tenant_id=tenant.id,
            )

    @pytest.mark.asyncio
    async def test_send_campaign_step_requires_default_audience(
        self, db_session: AsyncSession, test_user: User
    ):
        tenant = await _make_tenant(db_session, slug="noaud")
        db_session.add(MailchimpConnection(
            tenant_id=tenant.id,
            api_key="key-us19",
            server_prefix="us19",
            connected_by_id=test_user.id,
        ))
        template = EmailTemplate(
            name="x", subject_template="S", body_template="B"
        )
        db_session.add(template)
        await db_session.flush()
        campaign = Campaign(
            name="C", campaign_type="email",
            send_via="mailchimp", owner_id=test_user.id,
        )
        db_session.add(campaign)
        await db_session.commit()

        service = MailchimpService(db_session)
        with pytest.raises(MailchimpNotConnected):
            await service.send_campaign_step(
                campaign=campaign,
                template_id=template.id,
                sent_by_id=test_user.id,
                tenant_id=tenant.id,
            )


# ---------------------------------------------------------------------------
# sync_stats
# ---------------------------------------------------------------------------


class TestSyncStats:
    @pytest.mark.asyncio
    async def test_sync_stats_returns_aggregate_metrics(
        self, db_session: AsyncSession, test_user: User
    ):
        tenant = await _make_tenant(db_session, slug="stats")
        db_session.add(MailchimpConnection(
            tenant_id=tenant.id,
            api_key="key-us19",
            server_prefix="us19",
            connected_by_id=test_user.id,
            default_audience_id="list-1",
        ))
        campaign = Campaign(
            name="S", campaign_type="email",
            send_via="mailchimp", owner_id=test_user.id,
            mailchimp_campaign_id="mc-1",
        )
        db_session.add(campaign)
        await db_session.commit()

        transport = _route({
            ("GET", "/3.0/reports/mc-1"): {
                "emails_sent": 100,
                "opens": {"opens_total": 80, "unique_opens": 60, "open_rate": 0.6},
                "clicks": {"clicks_total": 25, "unique_clicks": 20, "click_rate": 0.2},
                "bounces": {"hard_bounces": 1, "soft_bounces": 2},
                "unsubscribed": 3,
            },
        })
        service = MailchimpService(db_session, client_factory=_factory(transport))
        stats = await service.sync_stats(campaign=campaign, tenant_id=tenant.id)

        assert stats["emails_sent"] == 100
        assert stats["opens"] == 80
        assert stats["unique_opens"] == 60
        assert stats["clicks"] == 25
        assert stats["bounces"] == 3
        assert stats["unsubscribes"] == 3
        assert campaign.num_sent == 100
