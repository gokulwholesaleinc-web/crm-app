"""Integration tests for the proposal duplicate endpoint.

Uses a real in-memory SQLite DB.
No mocks — assertions hit the actual database.
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

# Import all models so create_all picks them up
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
from src.contacts.models import Contact  # noqa: F401
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
from src.notifications.models import Notification  # noqa: F401
from src.opportunities.models import Opportunity, PipelineStage  # noqa: F401
from src.payments.models import Payment, Price, Product, StripeCustomer, Subscription  # noqa: F401
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
async def client(db_session: AsyncSession, test_engine) -> AsyncGenerator[AsyncClient, None]:
    from src.main import app

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession) -> User:
    user = User(
        email=f"user-{secrets.token_hex(4)}@test.com",
        hashed_password=get_password_hash("password"),
        full_name="Test User",
        is_active=True,
        is_approved=True,
        is_superuser=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def auth_headers(test_user: User) -> dict:
    token = create_access_token({"sub": str(test_user.id)})
    return {"Authorization": f"Bearer {token}"}


async def _make_proposal(
    db: AsyncSession,
    owner: User,
    *,
    title: str = "Original Proposal",
    status: str = "draft",
    amount: float | None = 500.0,
    signed_at=None,
) -> Proposal:
    proposal = Proposal(
        proposal_number=f"PR-{secrets.token_hex(4).upper()}",
        title=title,
        status=status,
        amount=amount,
        currency="USD",
        payment_type="one_time",
        executive_summary="Our exec summary",
        scope_of_work="Scope details here",
        terms="Net 30",
        owner_id=owner.id,
        created_by_id=owner.id,
        signed_at=signed_at,
    )
    db.add(proposal)
    await db.commit()
    await db.refresh(proposal)
    return proposal


class TestDuplicateEndpoint:

    async def test_returns_201_and_draft_clone(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User, auth_headers: dict
    ):
        proposal = await _make_proposal(db_session, test_user, title="Acme Proposal")

        resp = await client.post(
            f"/api/proposals/{proposal.id}/duplicate",
            headers=auth_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "Acme Proposal (copy)"
        assert data["status"] == "draft"

    async def test_clone_has_new_proposal_number(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User, auth_headers: dict
    ):
        proposal = await _make_proposal(db_session, test_user)

        resp = await client.post(
            f"/api/proposals/{proposal.id}/duplicate",
            headers=auth_headers,
        )
        data = resp.json()
        assert data["proposal_number"] != proposal.proposal_number

    async def test_clone_copies_core_content_fields(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User, auth_headers: dict
    ):
        proposal = await _make_proposal(db_session, test_user, title="Scope Test")

        resp = await client.post(
            f"/api/proposals/{proposal.id}/duplicate",
            headers=auth_headers,
        )
        data = resp.json()
        assert data["executive_summary"] == "Our exec summary"
        assert data["scope_of_work"] == "Scope details here"
        assert data["terms"] == "Net 30"
        assert data["amount"] is None

    async def test_clone_clears_esign_fields(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User, auth_headers: dict
    ):
        from datetime import UTC, datetime
        proposal = await _make_proposal(
            db_session, test_user, status="accepted", signed_at=datetime.now(UTC)
        )

        resp = await client.post(
            f"/api/proposals/{proposal.id}/duplicate",
            headers=auth_headers,
        )
        data = resp.json()
        assert data["status"] == "draft"
        assert data["signed_at"] is None
        assert data["signer_name"] is None
        assert data["signer_email"] is None
        assert data["sent_at"] is None
        assert data["accepted_at"] is None

    async def test_404_for_missing_proposal(
        self, client: AsyncClient, auth_headers: dict
    ):
        resp = await client.post(
            "/api/proposals/999999/duplicate",
            headers=auth_headers,
        )
        assert resp.status_code == 404

    async def test_401_without_auth(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        proposal = await _make_proposal(db_session, test_user)

        resp = await client.post(f"/api/proposals/{proposal.id}/duplicate")
        assert resp.status_code == 401

    async def test_audit_log_created(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User, auth_headers: dict
    ):
        from sqlalchemy import select as sa_select

        proposal = await _make_proposal(db_session, test_user)

        resp = await client.post(
            f"/api/proposals/{proposal.id}/duplicate",
            headers=auth_headers,
        )
        assert resp.status_code == 201
        clone_id = resp.json()["id"]

        result = await db_session.execute(
            sa_select(AuditLog).where(
                AuditLog.entity_type == "proposal",
                AuditLog.entity_id == clone_id,
                AuditLog.action == "create",
            )
        )
        log = result.scalars().first()
        assert log is not None

    async def test_duplicate_of_accepted_proposal_succeeds(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User, auth_headers: dict
    ):
        """Accepted (locked) proposals can still be cloned."""
        from datetime import UTC, datetime
        proposal = await _make_proposal(
            db_session, test_user, status="accepted", signed_at=datetime.now(UTC)
        )

        resp = await client.post(
            f"/api/proposals/{proposal.id}/duplicate",
            headers=auth_headers,
        )
        assert resp.status_code == 201
        assert resp.json()["status"] == "draft"
