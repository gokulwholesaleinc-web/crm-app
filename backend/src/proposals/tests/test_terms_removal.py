"""Removal of the redundant proposal Terms & Conditions agreement.

The binding terms already live inside the proposal document + ESIGN
disclosure, so the duplicate "I agree to the terms and conditions" gate
was retired. These no-mock tests pin the new contract:

* the public accept endpoint signs with the drawn signature alone — no
  ``agreed_to_terms`` field required;
* the T&C-agreement snapshot/consent timestamp are NOT captured going
  forward (set to None), while the ESIGN disclosure snapshot + version are
  still captured at accept (binding evidence kept);
* ``terms_and_conditions`` is no longer surfaced on the public proposal
  API response that feeds the sign modal.
"""

from __future__ import annotations

import base64
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
from src.auth.security import get_password_hash
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

_ONE_PIXEL_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010802000000907753de"
    "0000000c49444154789c63f8cfc0000003010100c9fe92ef0000000049454e44ae426082"
)
_SIGNATURE = "data:image/png;base64," + base64.b64encode(_ONE_PIXEL_PNG).decode()


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
    from src.main import app  # noqa: PLC0415

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


async def _make_sent_proposal(
    db: AsyncSession,
    owner: User,
    *,
    terms_and_conditions: str | None = None,
) -> Proposal:
    proposal = Proposal(
        proposal_number=f"PR-{secrets.token_hex(4).upper()}",
        public_token=secrets.token_urlsafe(24),
        title="Standalone Proposal",
        status="sent",
        sent_at=datetime.now(UTC),
        designated_signer_email="signer@example.com",
        owner_id=owner.id,
        created_by_id=owner.id,
        # Set a stale per-proposal T&C body to prove it is NOT snapshotted at
        # accept (and is no longer surfaced on the public API).
        terms_and_conditions=terms_and_conditions,
    )
    db.add(proposal)
    await db.commit()
    await db.refresh(proposal)
    return proposal


class TestTermsAgreementRemoval:
    async def test_accept_succeeds_without_agreed_to_terms_field(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        # The drawn signature alone must enable signing — the payload no
        # longer needs to carry the retired ``agreed_to_terms`` consent flag.
        proposal = await _make_sent_proposal(db_session, test_user)

        resp = await client.post(
            f"/api/proposals/public/{proposal.public_token}/accept",
            json={
                "signer_name": "Signer",
                "signer_email": "signer@example.com",
                "signature_image": _SIGNATURE,
            },
        )

        assert resp.status_code == 200, resp.text
        await db_session.refresh(proposal)
        assert proposal.status == "accepted"
        assert proposal.signature_image  # drawn signature persisted

    async def test_accept_does_not_capture_terms_snapshot_but_keeps_esign(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        # Going forward we stop capturing the redundant T&C-agreement
        # snapshot/consent timestamp, while the binding ESIGN disclosure
        # snapshot + version are still recorded as evidence.
        proposal = await _make_sent_proposal(
            db_session,
            test_user,
            terms_and_conditions="OLD redundant terms agreement body",
        )

        resp = await client.post(
            f"/api/proposals/public/{proposal.public_token}/accept",
            json={
                "signer_name": "Signer",
                "signer_email": "signer@example.com",
                "signature_image": _SIGNATURE,
            },
        )

        assert resp.status_code == 200, resp.text
        await db_session.refresh(proposal)
        # T&C-agreement capture retired.
        assert proposal.terms_and_conditions_snapshot is None
        assert proposal.agreed_to_terms_at is None
        # ESIGN disclosure evidence preserved.
        assert proposal.esign_disclosure_snapshot
        assert proposal.esign_disclosure_version
        assert proposal.signed_at is not None

    async def test_public_proposal_response_omits_terms_and_conditions(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        # The redundant agreement body is no longer surfaced on the public
        # API that feeds the sign modal. The real ``terms`` content section
        # of the document is unaffected (kept elsewhere).
        proposal = await _make_sent_proposal(
            db_session,
            test_user,
            terms_and_conditions="OLD redundant terms agreement body",
        )

        resp = await client.get(f"/api/proposals/public/{proposal.public_token}")

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "terms_and_conditions" not in data
        # ESIGN disclosure still surfaced for the public ceremony.
        assert "esign_disclosure" in data
