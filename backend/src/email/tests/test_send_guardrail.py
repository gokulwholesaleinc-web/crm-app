"""Tests for the assert_gmail_connected pre-flight guardrail.

Before this guardrail, user-initiated send paths (proposal, quote,
contract, /api/email/send) marked the target entity as "sent" even
when the operator's Gmail wasn't connected — the queue path swallowed
the error and parked the row in "retry" status.

Real SQLite + ASGI client; no mocks per CRM CLAUDE.md.
"""

from __future__ import annotations

import os
import secrets
import sys
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../../"))

from src.account.models import UserNotificationPrefs, UserPreferences  # noqa: F401
from src.activities.models import Activity  # noqa: F401
from src.assignment.models import AssignmentRule  # noqa: F401
from src.attachments.models import Attachment  # noqa: F401
from src.audit.models import AuditLog  # noqa: F401
from src.auth.models import User
from src.auth.security import create_access_token, get_password_hash
from src.campaigns.models import (  # noqa: F401
    Campaign,
    CampaignMember,
    EmailCampaignStep,
    EmailTemplate,
)
from src.comments.models import Comment  # noqa: F401
from src.companies.models import Company  # noqa: F401
from src.contacts.models import Contact
from src.contracts.models import Contract
from src.core.models import EntityShare, EntityTag, Note, Tag  # noqa: F401
from src.dashboard.models import (  # noqa: F401
    DashboardChart,
    DashboardNumberCard,
    DashboardReportWidget,
)
from src.database import Base, get_db
from src.email.models import EmailQueue, EmailSettings, InboundEmail  # noqa: F401
from src.email.service import assert_gmail_connected
from src.expenses.models import Expense  # noqa: F401
from src.filters.models import SavedFilter  # noqa: F401
from src.integrations.gmail.models import GmailConnection, GmailSyncState  # noqa: F401
from src.integrations.google_calendar.models import (  # noqa: F401
    CalendarSyncEvent,
    GoogleCalendarCredential,
)
from src.integrations.mailchimp.models import MailchimpConnection  # noqa: F401
from src.leads.models import Lead, LeadSource  # noqa: F401
from src.meta.models import CompanyMetaData, MetaCredential, MetaLeadCapture  # noqa: F401
from src.notifications.models import Notification  # noqa: F401
from src.opportunities.models import Opportunity, PipelineStage  # noqa: F401
from src.payments.models import (  # noqa: F401
    Payment,
    Price,
    Product,
    StripeCustomer,
    Subscription,
)
from src.proposals.models import Proposal
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
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    from src.main import app

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def user(db_session: AsyncSession) -> User:
    u = User(
        email=f"sender-{secrets.token_hex(3)}@test.com",
        hashed_password=get_password_hash("password"),
        full_name="Sender",
        is_active=True,
        is_approved=True,
        is_superuser=True,
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


@pytest_asyncio.fixture
async def auth_headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token({'sub': str(user.id)})}"}


async def _attach_gmail(db: AsyncSession, user: User) -> GmailConnection:
    conn = GmailConnection(
        user_id=user.id,
        email=user.email,
        access_token="x",
        refresh_token="y",
        scopes="https://www.googleapis.com/auth/gmail.send",
    )
    db.add(conn)
    await db.commit()
    return conn


async def _make_contact(db: AsyncSession, user: User, *, email: str | None = None) -> Contact:
    c = Contact(
        first_name="C",
        last_name="X",
        email=email or f"c-{secrets.token_hex(3)}@example.com",
        owner_id=user.id,
        created_by_id=user.id,
    )
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return c


class TestAssertGmailConnectedUnit:
    async def test_raises_when_no_connection(self, db_session: AsyncSession, user: User):
        with pytest.raises(ValueError, match="Gmail account is not connected"):
            await assert_gmail_connected(db_session, user.id)

    async def test_passes_when_connection_present(self, db_session: AsyncSession, user: User):
        await _attach_gmail(db_session, user)
        await assert_gmail_connected(db_session, user.id)  # no raise

    async def test_revoked_connection_treated_as_missing(
        self, db_session: AsyncSession, user: User
    ):
        conn = await _attach_gmail(db_session, user)
        conn.revoked_at = datetime.now(UTC)
        await db_session.commit()
        with pytest.raises(ValueError, match="Gmail account is not connected"):
            await assert_gmail_connected(db_session, user.id)


class TestProposalSendGuardrail:
    async def test_send_proposal_refuses_when_no_gmail(
        self, client: AsyncClient, db_session: AsyncSession, user: User, auth_headers: dict
    ):
        contact = await _make_contact(db_session, user)
        prop = Proposal(
            proposal_number=f"PR-{secrets.token_hex(3).upper()}",
            title="Test", status="draft",
            owner_id=user.id, created_by_id=user.id,
            contact_id=contact.id,
        )
        db_session.add(prop)
        await db_session.commit()
        await db_session.refresh(prop)

        resp = await client.post(
            f"/api/proposals/{prop.id}/send", headers=auth_headers, json={},
        )
        assert resp.status_code == 400
        assert "Gmail" in resp.json()["detail"]

        await db_session.refresh(prop)
        # Status stays draft — the whole point of the guardrail.
        assert prop.status == "draft"
        assert prop.sent_at is None


class TestEmailSendEndpointGuardrail:
    async def test_email_send_refuses_when_no_gmail(
        self, client: AsyncClient, user: User, auth_headers: dict
    ):
        resp = await client.post(
            "/api/email/send",
            headers=auth_headers,
            json={
                "to_email": "x@example.com",
                "subject": "hi",
                "body": "<p>hi</p>",
            },
        )
        assert resp.status_code == 400
        assert "Gmail" in resp.json()["detail"]


class TestContractSendGuardrail:
    async def test_contract_send_refuses_when_no_gmail(
        self, client: AsyncClient, db_session: AsyncSession, user: User, auth_headers: dict
    ):
        contact = await _make_contact(db_session, user)
        c = Contract(
            contract_number=f"CT-{secrets.token_hex(3).upper()}",
            title="Test", status="draft",
            owner_id=user.id, created_by_id=user.id,
            contact_id=contact.id,
        )
        db_session.add(c)
        await db_session.commit()
        await db_session.refresh(c)

        resp = await client.post(
            f"/api/contracts/{c.id}/send",
            headers=auth_headers,
            json={"to_email": "signer@example.com"},
        )
        assert resp.status_code == 400
        assert "Gmail" in resp.json()["detail"]

        await db_session.refresh(c)
        assert c.status == "draft"
        assert c.sent_at is None
        assert c.sign_token is None
