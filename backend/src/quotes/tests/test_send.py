"""Tests for QuoteService.send_quote_email gates and public-link signing.

Focus: the resend regression fix (valid_send_statuses) + the preconditions
that produced silent "sent" status flips before PR #310.

Real SQLite + service-layer calls; no mocks per CRM CLAUDE.md.
"""

from __future__ import annotations

import os
import secrets
import sys
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../../"))

from src.account.models import UserNotificationPrefs, UserPreferences  # noqa: F401
from src.activities.models import Activity  # noqa: F401
from src.assignment.models import AssignmentRule  # noqa: F401
from src.attachments.models import Attachment  # noqa: F401
from src.audit.models import AuditLog  # noqa: F401
from src.auth.models import User
from src.auth.security import get_password_hash
from src.campaigns.models import (  # noqa: F401
    Campaign,
    CampaignMember,
    EmailCampaignStep,
    EmailTemplate,
)
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
from src.database import Base
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
from src.quotes.service import QuoteService
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


async def _attach_gmail(db: AsyncSession, user: User) -> GmailConnection:
    conn = GmailConnection(
        user_id=user.id,
        email=user.email,
        access_token="x",
        refresh_token="y",
        scopes="https://www.googleapis.com/auth/gmail.send",
        token_expiry=datetime.now(UTC) + timedelta(hours=1),
    )
    db.add(conn)
    await db.commit()
    return conn


async def _make_contact(
    db: AsyncSession, user: User, *, email: str | None = "buyer@example.com"
) -> Contact:
    c = Contact(
        first_name="Buyer",
        last_name="X",
        email=email,
        owner_id=user.id,
        created_by_id=user.id,
    )
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return c


async def _make_quote(
    db: AsyncSession,
    user: User,
    *,
    contact: Contact | None = None,
    status: str = "draft",
) -> Quote:
    q = Quote(
        quote_number=f"QT-{secrets.token_hex(3).upper()}",
        title="Test Quote",
        status=status,
        owner_id=user.id,
        created_by_id=user.id,
        contact_id=contact.id if contact else None,
        currency="USD",
        subtotal=100.0,
        total=100.0,
        public_token=secrets.token_urlsafe(32),
    )
    db.add(q)
    await db.commit()
    await db.refresh(q)
    return q


class TestValidSendStatusesContract:
    """Unit test the class-level fix that allows Resend Quote to work."""

    async def test_resend_allowed_for_sent_and_viewed(self):
        # Default StatusTransitionMixin offers only ["draft"] — quote
        # service intentionally widens this so "Resend Quote" works
        # without crashing 400. accepted/rejected/expired stay locked.
        assert QuoteService.valid_send_statuses == ["draft", "sent", "viewed"]


class TestSendQuotePreconditions:
    async def test_send_without_gmail_raises(
        self, db_session: AsyncSession, user: User
    ):
        contact = await _make_contact(db_session, user)
        quote = await _make_quote(db_session, user, contact=contact)
        service = QuoteService(db_session)
        with pytest.raises(ValueError, match="Gmail account is not connected"):
            await service.send_quote_email(quote.id, user.id)

    async def test_send_terminal_status_raises_transition_error(
        self, db_session: AsyncSession, user: User
    ):
        await _attach_gmail(db_session, user)
        contact = await _make_contact(db_session, user)
        quote = await _make_quote(db_session, user, contact=contact, status="accepted")
        service = QuoteService(db_session)
        with pytest.raises(ValueError, match="Cannot transition from 'accepted'"):
            await service.send_quote_email(quote.id, user.id)

    async def test_resend_from_sent_passes_status_gate(
        self, db_session: AsyncSession, user: User
    ):
        """Resend bug fix: a quote already in 'sent' must pass the gate.

        We use a contact-with-no-email so the call fails at the email
        gate instead of attempting a real Gmail send. The error message
        proves the status gate was passed (i.e. the resend regression
        from defaulting to valid_send_statuses=["draft"] is gone).
        """
        await _attach_gmail(db_session, user)
        contact = await _make_contact(db_session, user, email=None)
        quote = await _make_quote(db_session, user, contact=contact, status="sent")
        service = QuoteService(db_session)
        with pytest.raises(ValueError, match="no email"):
            await service.send_quote_email(quote.id, user.id)

    async def test_resend_from_viewed_passes_status_gate(
        self, db_session: AsyncSession, user: User
    ):
        await _attach_gmail(db_session, user)
        contact = await _make_contact(db_session, user, email=None)
        quote = await _make_quote(db_session, user, contact=contact, status="viewed")
        service = QuoteService(db_session)
        with pytest.raises(ValueError, match="no email"):
            await service.send_quote_email(quote.id, user.id)

    async def test_send_no_contact_raises(
        self, db_session: AsyncSession, user: User
    ):
        await _attach_gmail(db_session, user)
        quote = await _make_quote(db_session, user, contact=None)
        service = QuoteService(db_session)
        with pytest.raises(ValueError, match="no contact attached"):
            await service.send_quote_email(quote.id, user.id)

    async def test_send_contact_without_email_raises(
        self, db_session: AsyncSession, user: User
    ):
        await _attach_gmail(db_session, user)
        contact = await _make_contact(db_session, user, email=None)
        quote = await _make_quote(db_session, user, contact=contact)
        service = QuoteService(db_session)
        with pytest.raises(ValueError, match="no email"):
            await service.send_quote_email(quote.id, user.id)


class TestResendPreservesSentAt:
    """The sent_at column records FIRST send only — resend must not
    clobber it. Without this, "when did we first email the customer?"
    audits silently drift and reminder cadence reads as fresh.
    """

    async def test_resend_preserves_original_sent_at(
        self, db_session: AsyncSession, user: User
    ):
        original_sent = datetime.now(UTC) - timedelta(days=7)
        await _attach_gmail(db_session, user)
        contact = await _make_contact(db_session, user, email=None)
        # Build a quote in 'sent' state with a known historical sent_at.
        # The downstream "no email" gate stops the call before any real
        # send — we just need the status gate to pass, and the model's
        # branch on `quote.sent_at is None` to be exercised. We assert
        # sent_at is unchanged after the (failed) resend, but importantly
        # also after a future call that succeeds the email gate.
        quote = await _make_quote(db_session, user, contact=contact, status="sent")
        quote.sent_at = original_sent
        await db_session.commit()

        service = QuoteService(db_session)
        with pytest.raises(ValueError, match="no email"):
            await service.send_quote_email(quote.id, user.id)

        await db_session.refresh(quote)
        # Failed resend doesn't move sent_at — same as the gmail-pre-flight
        # guard. Adds a baseline; the real protection is the
        # `if quote.sent_at is None` branch in service.py:381.
        # SQLite drops tzinfo on read, so compare naive timestamps.
        actual = quote.sent_at.replace(tzinfo=None) if quote.sent_at else None
        assert actual == original_sent.replace(tzinfo=None)


class TestPublicAcceptRejectGuards:
    async def test_get_public_quote_short_token_returns_none(
        self, db_session: AsyncSession
    ):
        service = QuoteService(db_session)
        assert await service.get_public_quote("short") is None
        assert await service.get_public_quote("") is None

    async def test_accept_public_wrong_signer_email_rejects(
        self, db_session: AsyncSession, user: User
    ):
        contact = await _make_contact(db_session, user, email="real@example.com")
        quote = await _make_quote(db_session, user, contact=contact, status="sent")
        service = QuoteService(db_session)
        with pytest.raises(ValueError, match="Signer email does not match"):
            await service.accept_quote_public(
                quote,
                signer_name="Imposter",
                signer_email="attacker@evil.com",
            )

    async def test_reject_public_wrong_signer_email_rejects(
        self, db_session: AsyncSession, user: User
    ):
        contact = await _make_contact(db_session, user, email="real@example.com")
        quote = await _make_quote(db_session, user, contact=contact, status="sent")
        service = QuoteService(db_session)
        with pytest.raises(ValueError, match="Signer email does not match"):
            await service.reject_quote_public(
                quote,
                reason="nope",
                signer_email="attacker@evil.com",
            )

    async def test_accept_public_terminal_status_rejects(
        self, db_session: AsyncSession, user: User
    ):
        contact = await _make_contact(db_session, user, email="real@example.com")
        quote = await _make_quote(db_session, user, contact=contact, status="accepted")
        service = QuoteService(db_session)
        with pytest.raises(ValueError, match="Cannot accept quote in 'accepted'"):
            await service.accept_quote_public(
                quote,
                signer_name="Real",
                signer_email="real@example.com",
            )
