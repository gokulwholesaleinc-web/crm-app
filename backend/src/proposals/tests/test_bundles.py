"""Proposal bundle backend behavior."""

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
from sqlalchemy import select
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
from src.proposals.models import Proposal, ProposalBundle
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


@pytest_asyncio.fixture
async def auth_headers(test_user: User) -> dict:
    token = create_access_token({"sub": str(test_user.id)})
    return {"Authorization": f"Bearer {token}"}


async def _make_proposal(
    db: AsyncSession,
    owner: User,
    *,
    title: str = "Bundle Option",
    status: str = "draft",
) -> Proposal:
    proposal = Proposal(
        proposal_number=f"PR-{secrets.token_hex(4).upper()}",
        public_token=secrets.token_urlsafe(24),
        title=title,
        status=status,
        designated_signer_email="signer@example.com",
        owner_id=owner.id,
        created_by_id=owner.id,
    )
    db.add(proposal)
    await db.commit()
    await db.refresh(proposal)
    return proposal


async def _make_bundle(
    db: AsyncSession,
    owner: User,
    proposals: list[Proposal],
    *,
    status: str = "draft",
) -> ProposalBundle:
    bundle = ProposalBundle(
        bundle_number=f"PB-{secrets.token_hex(4).upper()}",
        public_token=secrets.token_urlsafe(24),
        title="Proposal Options",
        status=status,
        owner_id=owner.id,
        created_by_id=owner.id,
    )
    db.add(bundle)
    await db.flush()
    for index, proposal in enumerate(proposals):
        proposal.proposal_bundle_id = bundle.id
        proposal.bundle_sort_order = index
        proposal.bundle_is_recommended = index == 0
        proposal.status = status if status in {"sent", "viewed"} else proposal.status
        proposal.sent_at = datetime.now(UTC) if status in {"sent", "viewed"} else None
    await db.commit()
    await db.refresh(bundle)
    return bundle


class TestProposalBundles:
    async def test_model_metadata_has_bundle_table_and_no_package_tables(self):
        assert "proposal_bundles" in Base.metadata.tables
        assert "proposal_packages" not in Base.metadata.tables
        assert "proposal_package_items" not in Base.metadata.tables
        assert "proposal_bundle_id" in Base.metadata.tables["proposals"].c

    async def test_create_bundle_groups_real_draft_proposals(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        auth_headers: dict,
    ):
        first = await _make_proposal(db_session, test_user, title="Good")
        second = await _make_proposal(db_session, test_user, title="Better")

        resp = await client.post(
            "/api/proposals/bundles",
            headers=auth_headers,
            json={
                "title": "Two ways to move forward",
                "proposal_ids": [first.id, second.id],
            },
        )

        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "Two ways to move forward"
        assert [p["id"] for p in data["proposals"]] == [first.id, second.id]
        await db_session.refresh(first)
        await db_session.refresh(second)
        assert first.proposal_bundle_id == data["id"]
        assert second.proposal_bundle_id == data["id"]
        assert first.bundle_is_recommended is True

    async def test_public_bundle_response_exposes_real_proposal_options(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        first = await _make_proposal(db_session, test_user, title="Lean Option")
        second = await _make_proposal(db_session, test_user, title="Full Option")
        bundle = await _make_bundle(db_session, test_user, [first, second], status="sent")

        resp = await client.get(f"/api/proposals/public/{bundle.public_token}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["bundle_id"] == bundle.id
        assert data["proposal_number"] == bundle.bundle_number
        assert [p["title"] for p in data["proposal_options"]] == [
            "Lean Option",
            "Full Option",
        ]
        assert data["proposal_options"][0]["public_token"] == first.public_token
        assert data["payment_type"] is None
        assert data["stripe_payment_url"] is None

    async def test_accepting_one_bundled_proposal_rejects_siblings(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        first = await _make_proposal(db_session, test_user, title="Selected", status="sent")
        second = await _make_proposal(db_session, test_user, title="Not Selected", status="sent")
        bundle = await _make_bundle(db_session, test_user, [first, second], status="sent")
        signature = "data:image/png;base64," + base64.b64encode(_ONE_PIXEL_PNG).decode()

        resp = await client.post(
            f"/api/proposals/public/{first.public_token}/accept",
            json={
                "signer_name": "Signer",
                "signer_email": "signer@example.com",
                "signature_image": signature,
                "agreed_to_terms": True,
                "selected_proposal_id": first.id,
            },
        )

        assert resp.status_code == 200
        await db_session.refresh(first)
        await db_session.refresh(second)
        await db_session.refresh(bundle)
        assert first.status == "accepted"
        assert second.status == "rejected"
        assert bundle.status == "accepted"
        assert bundle.selected_proposal_id == first.id
        activity = (
            await db_session.execute(
                select(Activity).where(
                    Activity.entity_type == "proposals",
                    Activity.entity_id == first.id,
                    Activity.subject.like("Proposal bundle selected:%"),
                )
            )
        ).scalar_one_or_none()
        assert activity is not None
