"""Integration tests for campaign execute -> send_via routing.

Asserts POST /api/campaigns/{id}/execute and CampaignService._send_step
honor `campaign.send_via`. Real in-memory SQLite, no mocks.
"""

from __future__ import annotations

import os
import secrets
import sys
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../../"))

# Import all models so create_all picks them up
from src.account.models import UserNotificationPrefs, UserPreferences  # noqa: F401
from src.activities.models import Activity  # noqa: F401
from src.assignment.models import AssignmentRule  # noqa: F401
from src.attachments.models import Attachment  # noqa: F401
from src.audit.models import AuditLog  # noqa: F401
from src.auth.models import User
from src.auth.security import create_access_token, get_password_hash
from src.campaigns.models import (
    Campaign,
    CampaignMember,
    EmailCampaignStep,
    EmailTemplate,
)
from src.campaigns.service import CampaignService, EmailCampaignStepService
from src.comments.models import Comment  # noqa: F401
from src.companies.models import Company  # noqa: F401
from src.contacts.models import Contact
from src.contracts.models import Contract  # noqa: F401
from src.core.models import EntityShare, EntityTag, Note, Tag  # noqa: F401
from src.dashboard.models import (  # noqa: F401
    DashboardChart,
    DashboardNumberCard,
    DashboardReportWidget,
)
from src.database import Base, get_db
from src.email.models import EmailQueue, EmailSettings, InboundEmail  # noqa: F401
from src.expenses.models import Expense  # noqa: F401
from src.filters.models import SavedFilter  # noqa: F401
from src.integrations.gmail.models import GmailConnection, GmailSyncState  # noqa: F401
from src.integrations.google_calendar.models import (  # noqa: F401
    CalendarSyncEvent,
    GoogleCalendarCredential,
)
from src.integrations.mailchimp.models import MailchimpConnection  # noqa: F401
from src.integrations.mailchimp.service import MailchimpNotConnected
from src.leads.models import Lead, LeadSource  # noqa: F401
from src.meta.models import CompanyMetaData, MetaCredential, MetaLeadCapture  # noqa: F401
from src.notifications.models import Notification  # noqa: F401
from src.opportunities.models import Opportunity, PipelineStage  # noqa: F401
from src.payments.models import Payment, Price, Product, StripeCustomer, Subscription  # noqa: F401
from src.proposals.models import Proposal  # noqa: F401
from src.quotes.models import (  # noqa: F401
    ProductBundle,
    ProductBundleItem,
    Quote,
    QuoteLineItem,
    QuoteTemplate,
)
from src.reports.models import SavedReport  # noqa: F401
from src.roles.models import DEFAULT_PERMISSIONS, Role, RoleName, UserRole  # noqa: F401
from src.sequences.models import Sequence, SequenceEnrollment  # noqa: F401
from src.webhooks.models import Webhook, WebhookDelivery  # noqa: F401
from src.whitelabel.models import Tenant, TenantSettings, TenantUser  # noqa: F401
from src.workflows.models import WorkflowExecution, WorkflowRule  # noqa: F401

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession, test_engine) -> AsyncGenerator[AsyncClient, None]:
    from src.main import app

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession) -> User:
    user = User(
        email=f"admin-{secrets.token_hex(4)}@test.com",
        hashed_password=get_password_hash("password"),
        full_name="Admin User",
        is_active=True,
        is_approved=True,
        is_superuser=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def auth_headers(admin_user: User) -> dict:
    token = create_access_token({"sub": str(admin_user.id)})
    return {"Authorization": f"Bearer {token}"}


async def _make_campaign_with_step(
    db: AsyncSession,
    owner: User,
    *,
    send_via: str,
    member_contact: Contact | None = None,
) -> Campaign:
    template = EmailTemplate(
        name=f"tmpl-{secrets.token_hex(3)}",
        subject_template="Hello {{name}}",
        body_template="<p>Hi there</p>",
        created_by_id=owner.id,
    )
    db.add(template)
    await db.flush()

    campaign = Campaign(
        name=f"camp-{secrets.token_hex(3)}",
        campaign_type="email",
        status="planned",
        send_via=send_via,
        owner_id=owner.id,
        created_by_id=owner.id,
    )
    db.add(campaign)
    await db.flush()

    step = EmailCampaignStep(
        campaign_id=campaign.id,
        step_order=0,
        template_id=template.id,
        delay_days=0,
    )
    db.add(step)

    if member_contact is not None:
        db.add(
            CampaignMember(
                campaign_id=campaign.id,
                member_type="contact",
                member_id=member_contact.id,
            )
        )

    await db.commit()
    await db.refresh(campaign)
    return campaign


async def _make_contact(db: AsyncSession, owner: User, *, email: str | None) -> Contact:
    contact = Contact(
        first_name="Test",
        last_name="Contact",
        email=email,
        owner_id=owner.id,
        created_by_id=owner.id,
    )
    db.add(contact)
    await db.commit()
    await db.refresh(contact)
    return contact


class TestExecuteSendViaRouting:
    async def test_mailchimp_path_taken_when_send_via_is_mailchimp(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        auth_headers: dict,
    ):
        contact = await _make_contact(db_session, admin_user, email="x@example.com")
        campaign = await _make_campaign_with_step(
            db_session, admin_user, send_via="mailchimp", member_contact=contact,
        )

        resp = await client.post(
            f"/api/campaigns/{campaign.id}/execute", headers=auth_headers,
        )

        # Mailchimp branch raises MailchimpNotConnected (no tenant/connection
        # in test env); the endpoint catches it and pauses. The error text
        # identifies which branch ran — Gmail would say "active Gmail connection".
        assert resp.status_code == 200
        body = resp.json()
        assert "execution failed" in body["message"].lower()
        assert "mailchimp" in body["message"].lower()

        await db_session.refresh(campaign)
        assert campaign.status == "paused"
        assert campaign.is_executing is False

    async def test_gmail_path_taken_when_send_via_is_gmail(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        auth_headers: dict,
    ):
        contact = await _make_contact(db_session, admin_user, email="y@example.com")
        campaign = await _make_campaign_with_step(
            db_session, admin_user, send_via="gmail", member_contact=contact,
        )

        resp = await client.post(
            f"/api/campaigns/{campaign.id}/execute", headers=auth_headers,
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["send_via"] == "gmail"
        assert body["emails_sent"] == 1

        # Mailchimp branch never writes to EmailQueue, so a queued row proves
        # the Gmail branch ran.
        queued = await db_session.execute(
            select(EmailQueue).where(EmailQueue.campaign_id == campaign.id)
        )
        rows = queued.scalars().all()
        assert len(rows) == 1
        assert rows[0].to_email == "y@example.com"

    async def test_send_via_unit_routes_on_campaign_flag(
        self, db_session: AsyncSession, admin_user: User,
    ):
        contact = await _make_contact(db_session, admin_user, email="z@example.com")
        service = CampaignService(db_session)
        step_service = EmailCampaignStepService(db_session)

        mc_campaign = await _make_campaign_with_step(
            db_session, admin_user, send_via="mailchimp", member_contact=contact,
        )
        mc_steps = await step_service.get_steps(mc_campaign.id)
        with pytest.raises(MailchimpNotConnected):
            await service._send_step(
                campaign=mc_campaign, step=mc_steps[0], sent_by_id=admin_user.id,
            )

        gmail_campaign = await _make_campaign_with_step(
            db_session, admin_user, send_via="gmail", member_contact=contact,
        )
        gmail_steps = await step_service.get_steps(gmail_campaign.id)
        emails_sent = await service._send_step(
            campaign=gmail_campaign, step=gmail_steps[0], sent_by_id=admin_user.id,
        )
        assert emails_sent == 1
        assert gmail_campaign.num_sent == 1

    async def test_gmail_send_attributes_to_manual_clicker_not_owner(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        auth_headers: dict,
    ):
        # Campaign owned by a *different* user; the clicker (admin_user) is
        # the one we want recorded on the queued mail.
        owner = User(
            email=f"owner-{secrets.token_hex(3)}@test.com",
            hashed_password=get_password_hash("password"),
            full_name="Owner User",
            is_active=True,
            is_approved=True,
            is_superuser=True,
        )
        db_session.add(owner)
        await db_session.commit()
        await db_session.refresh(owner)

        contact = await _make_contact(db_session, owner, email="w@example.com")
        campaign = await _make_campaign_with_step(
            db_session, owner, send_via="gmail", member_contact=contact,
        )

        resp = await client.post(
            f"/api/campaigns/{campaign.id}/execute", headers=auth_headers,
        )
        assert resp.status_code == 200

        queued = await db_session.execute(
            select(EmailQueue).where(EmailQueue.campaign_id == campaign.id)
        )
        rows = queued.scalars().all()
        assert len(rows) == 1
        # The queued row's sent_by_id is the clicker, not the owner —
        # otherwise a manager triggering someone else's campaign would
        # attribute the mail to the wrong inbox / signature.
        assert rows[0].sent_by_id == admin_user.id

    async def test_is_executing_flag_resets_on_failure(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        auth_headers: dict,
    ):
        # Mailchimp path with no tenant → MailchimpNotConnected → endpoint
        # catches in the except branch. The finally block must reset
        # is_executing so a re-trigger isn't permanently blocked.
        contact = await _make_contact(db_session, admin_user, email="r@example.com")
        campaign = await _make_campaign_with_step(
            db_session, admin_user, send_via="mailchimp", member_contact=contact,
        )

        resp = await client.post(
            f"/api/campaigns/{campaign.id}/execute", headers=auth_headers,
        )
        assert resp.status_code == 200
        await db_session.refresh(campaign)
        assert campaign.is_executing is False
        assert campaign.status == "paused"

        # Re-trigger: must NOT short-circuit on "already executing".
        resp2 = await client.post(
            f"/api/campaigns/{campaign.id}/execute", headers=auth_headers,
        )
        assert resp2.status_code == 200
        assert "already executing" not in resp2.json()["message"].lower()
