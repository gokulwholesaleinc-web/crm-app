"""Integration tests for notification entity_label + entity_link enrichment.

Verifies the list endpoint resolves (entity_type, entity_id) into a
display label + frontend route via `core.entity_links.fill_entity_labels`.
Real SQLite + ASGI; no mocks per CRM CLAUDE.md.
"""

from __future__ import annotations

import os
import secrets
import sys
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../../"))

from src.account.models import UserNotificationPrefs, UserPreferences  # noqa: F401
from src.activities.models import Activity
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
from src.companies.models import Company
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
from src.leads.models import Lead, LeadSource  # noqa: F401
from src.meta.models import CompanyMetaData, MetaCredential, MetaLeadCapture  # noqa: F401
from src.notifications.models import Notification
from src.opportunities.models import Opportunity, PipelineStage  # noqa: F401
from src.payments.models import (  # noqa: F401
    Payment,
    Price,
    Product,
    StripeCustomer,
    Subscription,
)
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


@pytest_asyncio.fixture
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
        email=f"u-{secrets.token_hex(3)}@test.com",
        hashed_password=get_password_hash("password"),
        full_name="Test User",
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


async def _make_notification(
    db: AsyncSession,
    user: User,
    *,
    entity_type: str | None,
    entity_id: int | None,
    title: str = "Test",
) -> Notification:
    n = Notification(
        user_id=user.id,
        type="generic",
        title=title,
        message="hello",
        entity_type=entity_type,
        entity_id=entity_id,
        is_read=False,
    )
    db.add(n)
    await db.commit()
    await db.refresh(n)
    return n


class TestNotificationEntityLinkEnrichment:
    async def test_contact_notification_gets_label_and_link(
        self, client: AsyncClient, db_session: AsyncSession, user: User, auth_headers: dict,
    ):
        contact = Contact(
            first_name="Acme", last_name="Lead",
            email=f"c-{secrets.token_hex(3)}@example.com",
            owner_id=user.id, created_by_id=user.id,
        )
        db_session.add(contact)
        await db_session.commit()
        await db_session.refresh(contact)

        await _make_notification(
            db_session, user, entity_type="contacts", entity_id=contact.id,
        )

        resp = await client.get("/api/notifications", headers=auth_headers)
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["entity_label"] == "Acme Lead"
        assert items[0]["entity_link"] == f"/contacts/{contact.id}"

    async def test_company_notification_uses_company_name(
        self, client: AsyncClient, db_session: AsyncSession, user: User, auth_headers: dict,
    ):
        company = Company(
            name="Stark Industries", owner_id=user.id, created_by_id=user.id,
        )
        db_session.add(company)
        await db_session.commit()
        await db_session.refresh(company)

        await _make_notification(
            db_session, user, entity_type="company", entity_id=company.id,
        )

        resp = await client.get("/api/notifications", headers=auth_headers)
        items = resp.json()["items"]
        # The singular "company" alias resolves to the canonical "companies"
        # plural; the link uses the plural URL prefix.
        assert items[0]["entity_label"] == "Stark Industries"
        assert items[0]["entity_link"] == f"/companies/{company.id}"

    async def test_unroutable_entity_type_returns_null_label_and_link(
        self, client: AsyncClient, db_session: AsyncSession, user: User, auth_headers: dict,
    ):
        # 'users' is not in ROUTABLE_ENTITY_PLURALS — verified privacy
        # property: a notification anchored on another user produces no
        # clickable affordance, just title + message.
        await _make_notification(
            db_session, user, entity_type="users", entity_id=999,
        )

        resp = await client.get("/api/notifications", headers=auth_headers)
        items = resp.json()["items"]
        assert items[0]["entity_label"] is None
        assert items[0]["entity_link"] is None

    async def test_activity_notification_routes_to_activities_page(
        self, client: AsyncClient, db_session: AsyncSession, user: User, auth_headers: dict,
    ):
        # "Activity due" notifications carry entity_type="activities". The
        # old hand-rolled route map in NotificationBell handled this; verify
        # the server-side resolver does too (regression caught by trio).
        activity = Activity(
            activity_type="task",
            subject="Follow up with prospect",
            entity_type="contacts",
            entity_id=1,
            owner_id=user.id,
            created_by_id=user.id,
        )
        db_session.add(activity)
        await db_session.commit()
        await db_session.refresh(activity)

        await _make_notification(
            db_session, user, entity_type="activities", entity_id=activity.id,
        )

        resp = await client.get("/api/notifications", headers=auth_headers)
        items = resp.json()["items"]
        assert items[0]["entity_label"] == "Follow up with prospect"
        assert items[0]["entity_link"] == f"/activities/{activity.id}"

    async def test_missing_row_gets_fallback_label(
        self, client: AsyncClient, db_session: AsyncSession, user: User, auth_headers: dict,
    ):
        # Routable type but the referenced contact has been deleted —
        # we want a stable fallback "Contact #N" so the notification still
        # makes sense to the user.
        await _make_notification(
            db_session, user, entity_type="contacts", entity_id=99999,
        )

        resp = await client.get("/api/notifications", headers=auth_headers)
        items = resp.json()["items"]
        assert items[0]["entity_label"] == "Contact #99999"
        assert items[0]["entity_link"] == "/contacts/99999"
