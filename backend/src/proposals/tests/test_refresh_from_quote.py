"""Integration tests for the refresh-from-quote endpoint and helper.

Uses a real in-memory SQLite DB (same approach as the project-level test suite).
No mocks — assertions hit the actual database.
"""

from __future__ import annotations

import os
import secrets
import sys
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../../"))

from src.auth.models import User, RejectedAccessEmail
from src.auth.security import create_access_token, get_password_hash
from src.contacts.models import Contact
from src.companies.models import Company
from src.database import Base, get_db
from src.proposals.models import Proposal, ProposalTemplate, ProposalView
from src.proposals.refresh import refresh_proposal_from_quote
from src.quotes.models import Quote, QuoteLineItem, QuoteTemplate, ProductBundle, ProductBundleItem
from src.whitelabel.models import Tenant, TenantSettings, TenantUser

# Import all models so create_all picks them up
from src.activities.models import Activity  # noqa: F401
from src.campaigns.models import Campaign, CampaignMember, EmailTemplate, EmailCampaignStep  # noqa: F401
from src.core.models import Note, Tag, EntityTag, EntityShare  # noqa: F401
from src.workflows.models import WorkflowRule, WorkflowExecution  # noqa: F401
from src.dashboard.models import DashboardNumberCard, DashboardChart, DashboardReportWidget  # noqa: F401
from src.attachments.models import Attachment  # noqa: F401
from src.email.models import EmailQueue, InboundEmail, EmailSettings  # noqa: F401
from src.notifications.models import Notification  # noqa: F401
from src.account.models import UserNotificationPrefs, UserPreferences  # noqa: F401
from src.filters.models import SavedFilter  # noqa: F401
from src.reports.models import SavedReport  # noqa: F401
from src.audit.models import AuditLog  # noqa: F401
from src.comments.models import Comment  # noqa: F401
from src.roles.models import Role, UserRole, RoleName, DEFAULT_PERMISSIONS  # noqa: F401
from src.webhooks.models import Webhook, WebhookDelivery  # noqa: F401
from src.assignment.models import AssignmentRule  # noqa: F401
from src.sequences.models import Sequence, SequenceEnrollment  # noqa: F401
from src.payments.models import StripeCustomer, Product, Price, Payment, Subscription  # noqa: F401
from src.contracts.models import Contract  # noqa: F401
from src.leads.models import Lead, LeadSource  # noqa: F401
from src.opportunities.models import Opportunity, PipelineStage  # noqa: F401
from src.meta.models import CompanyMetaData, MetaCredential, MetaLeadCapture  # noqa: F401
from src.expenses.models import Expense  # noqa: F401
from src.integrations.google_calendar.models import GoogleCalendarCredential, CalendarSyncEvent  # noqa: F401
from src.integrations.gmail.models import GmailConnection, GmailSyncState  # noqa: F401
from src.integrations.mailchimp.models import MailchimpConnection  # noqa: F401

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


async def _make_quote(db: AsyncSession, owner: User, total: float = 1000.0) -> Quote:
    quote = Quote(
        quote_number=f"QT-{secrets.token_hex(4).upper()}",
        title="Test Quote",
        status="draft",
        currency="USD",
        payment_type="one_time",
        subtotal=total,
        total=total,
        owner_id=owner.id,
        created_by_id=owner.id,
    )
    db.add(quote)
    await db.commit()
    await db.refresh(quote)
    return quote


async def _make_proposal(
    db: AsyncSession,
    owner: User,
    quote: Quote | None = None,
    status: str = "draft",
    amount: float = 500.0,
) -> Proposal:
    proposal = Proposal(
        proposal_number=f"PR-{secrets.token_hex(4).upper()}",
        title="Test Proposal",
        status=status,
        amount=amount,
        currency="USD",
        payment_type="one_time",
        quote_id=quote.id if quote else None,
        owner_id=owner.id,
        created_by_id=owner.id,
    )
    db.add(proposal)
    await db.commit()
    await db.refresh(proposal)
    return proposal


# ---------------------------------------------------------------------------
# Unit-style tests for the helper function
# ---------------------------------------------------------------------------

class TestRefreshProposalFromQuoteHelper:

    async def test_refreshes_amount_from_quote_total(
        self, db_session: AsyncSession, test_user: User
    ):
        quote = await _make_quote(db_session, test_user, total=2500.0)
        proposal = await _make_proposal(db_session, test_user, quote=quote, amount=500.0)

        updated = await refresh_proposal_from_quote(db_session, proposal)

        assert float(updated.amount) == 2500.0

    async def test_refreshes_currency_from_quote(
        self, db_session: AsyncSession, test_user: User
    ):
        quote = await _make_quote(db_session, test_user)
        quote.currency = "EUR"
        await db_session.commit()
        await db_session.refresh(quote)

        proposal = await _make_proposal(db_session, test_user, quote=quote)
        proposal.currency = "USD"
        await db_session.commit()

        updated = await refresh_proposal_from_quote(db_session, proposal)
        assert updated.currency == "EUR"

    async def test_refreshes_payment_type_and_recurring(
        self, db_session: AsyncSession, test_user: User
    ):
        quote = await _make_quote(db_session, test_user)
        quote.payment_type = "subscription"
        quote.recurring_interval = "month"
        quote.recurring_interval_count = 3
        await db_session.commit()
        await db_session.refresh(quote)

        proposal = await _make_proposal(db_session, test_user, quote=quote)

        updated = await refresh_proposal_from_quote(db_session, proposal)
        assert updated.payment_type == "subscription"
        assert updated.recurring_interval == "month"
        assert updated.recurring_interval_count == 3

    async def test_raises_value_error_when_no_quote_link(
        self, db_session: AsyncSession, test_user: User
    ):
        proposal = await _make_proposal(db_session, test_user, quote=None)
        with pytest.raises(ValueError, match="not linked to a quote"):
            await refresh_proposal_from_quote(db_session, proposal)

    async def test_raises_value_error_for_locked_status(
        self, db_session: AsyncSession, test_user: User
    ):
        quote = await _make_quote(db_session, test_user)
        for locked_status in ("signed", "accepted", "awaiting_payment", "paid"):
            proposal = await _make_proposal(
                db_session, test_user, quote=quote, status=locked_status
            )
            with pytest.raises(ValueError, match=locked_status):
                await refresh_proposal_from_quote(db_session, proposal)

    async def test_raises_lookup_error_when_quote_deleted(
        self, db_session: AsyncSession, test_user: User
    ):
        quote = await _make_quote(db_session, test_user)
        proposal = await _make_proposal(db_session, test_user, quote=quote)
        # Detach quote_id reference without triggering FK cascade
        proposal.quote_id = 999999
        await db_session.flush()

        with pytest.raises(LookupError):
            await refresh_proposal_from_quote(db_session, proposal)

    async def test_does_not_touch_other_fields(
        self, db_session: AsyncSession, test_user: User
    ):
        quote = await _make_quote(db_session, test_user, total=750.0)
        proposal = await _make_proposal(db_session, test_user, quote=quote)
        proposal.designated_signer_email = "signer@example.com"
        proposal.valid_until = None
        proposal.title = "Keep This Title"
        await db_session.commit()

        updated = await refresh_proposal_from_quote(db_session, proposal)

        assert updated.designated_signer_email == "signer@example.com"
        assert updated.title == "Keep This Title"


# ---------------------------------------------------------------------------
# HTTP endpoint tests
# ---------------------------------------------------------------------------

class TestRefreshFromQuoteEndpoint:

    async def test_returns_200_and_updated_proposal(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User, auth_headers: dict
    ):
        quote = await _make_quote(db_session, test_user, total=3000.0)
        proposal = await _make_proposal(db_session, test_user, quote=quote, amount=100.0)

        resp = await client.post(
            f"/api/proposals/{proposal.id}/refresh-from-quote",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert float(data["amount"]) == 3000.0

    async def test_404_for_missing_proposal(
        self, client: AsyncClient, auth_headers: dict
    ):
        resp = await client.post(
            "/api/proposals/999999/refresh-from-quote",
            headers=auth_headers,
        )
        assert resp.status_code == 404

    async def test_400_when_no_quote_link(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User, auth_headers: dict
    ):
        proposal = await _make_proposal(db_session, test_user, quote=None)

        resp = await client.post(
            f"/api/proposals/{proposal.id}/refresh-from-quote",
            headers=auth_headers,
        )
        assert resp.status_code == 400
        assert "not linked" in resp.json()["detail"]

    async def test_400_for_locked_proposal(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User, auth_headers: dict
    ):
        quote = await _make_quote(db_session, test_user)
        proposal = await _make_proposal(
            db_session, test_user, quote=quote, status="accepted"
        )

        resp = await client.post(
            f"/api/proposals/{proposal.id}/refresh-from-quote",
            headers=auth_headers,
        )
        assert resp.status_code == 400
        assert "accepted" in resp.json()["detail"]

    async def test_409_when_quote_deleted(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User, auth_headers: dict
    ):
        quote = await _make_quote(db_session, test_user)
        proposal = await _make_proposal(db_session, test_user, quote=quote)
        # Point to a nonexistent quote
        proposal.quote_id = 999998
        await db_session.commit()

        resp = await client.post(
            f"/api/proposals/{proposal.id}/refresh-from-quote",
            headers=auth_headers,
        )
        assert resp.status_code == 409

    async def test_401_without_auth(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        quote = await _make_quote(db_session, test_user)
        proposal = await _make_proposal(db_session, test_user, quote=quote)

        resp = await client.post(
            f"/api/proposals/{proposal.id}/refresh-from-quote",
        )
        assert resp.status_code == 401

    async def test_audit_log_created(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User, auth_headers: dict
    ):
        from sqlalchemy import select as sa_select
        from src.audit.models import AuditLog

        quote = await _make_quote(db_session, test_user, total=8000.0)
        proposal = await _make_proposal(db_session, test_user, quote=quote, amount=100.0)

        await client.post(
            f"/api/proposals/{proposal.id}/refresh-from-quote",
            headers=auth_headers,
        )

        result = await db_session.execute(
            sa_select(AuditLog).where(
                AuditLog.entity_type == "proposal",
                AuditLog.entity_id == proposal.id,
                AuditLog.action == "update",
            )
        )
        log = result.scalars().first()
        assert log is not None
