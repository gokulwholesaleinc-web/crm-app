"""Proposal package backend behavior.

Uses a real in-memory SQLite DB for router/service paths so package
ownership, public response filtering, and accept-time snapshot persistence
exercise the same code the app uses.
"""

from __future__ import annotations

import base64
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
from src.proposals.models import Proposal, ProposalPackage, ProposalPackageItem
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
    status: str = "draft",
    amount: float | None = None,
    stripe_payment_url: str | None = None,
) -> Proposal:
    proposal = Proposal(
        proposal_number=f"PR-{secrets.token_hex(4).upper()}",
        public_token=secrets.token_urlsafe(24),
        title="Package Proposal",
        status=status,
        amount=amount,
        currency="USD",
        payment_type="one_time",
        stripe_payment_url=stripe_payment_url,
        designated_signer_email="signer@example.com",
        owner_id=owner.id,
        created_by_id=owner.id,
    )
    db.add(proposal)
    await db.commit()
    await db.refresh(proposal)
    return proposal


async def _add_package(
    db: AsyncSession,
    proposal: Proposal,
    *,
    name: str = "Growth Package",
    is_active: bool = True,
    is_recommended: bool = False,
) -> ProposalPackage:
    package = ProposalPackage(
        proposal_id=proposal.id,
        name=name,
        currency="USD",
        payment_type="one_time",
        subtotal=1000,
        discount_amount=100,
        tax_amount=0,
        total=900,
        sort_order=1,
        is_active=is_active,
        is_recommended=is_recommended,
        items=[
            ProposalPackageItem(
                description="Implementation",
                quantity=1,
                unit_price=1000,
                discount_amount=100,
                total=900,
                sort_order=1,
            )
        ],
    )
    db.add(package)
    await db.commit()
    await db.refresh(package)
    return package


def _package_payload(**overrides):
    payload = {
        "name": "Growth Package",
        "currency": "USD",
        "payment_type": "one_time",
        "sort_order": 2,
        "is_recommended": True,
        "subtotal": "9999.00",
        "total": "9999.00",
        "items": [
            {
                "description": "Implementation",
                "quantity": "2.00",
                "unit_price": "500.00",
                "discount_amount": "125.00",
                "total": "1.00",
                "sort_order": 1,
            }
        ],
    }
    payload.update(overrides)
    return payload


class TestProposalPackages:
    async def test_model_metadata_has_package_tables_and_partial_index(self):
        assert "proposal_packages" in Base.metadata.tables
        assert "proposal_package_items" in Base.metadata.tables
        assert "selected_package_id" in Base.metadata.tables["proposals"].c
        indexes = {idx.name: idx for idx in Base.metadata.tables["proposal_packages"].indexes}
        assert "uq_proposal_packages_one_recommended" in indexes
        assert indexes["uq_proposal_packages_one_recommended"].unique is True

    async def test_create_package_recomputes_totals_and_ignores_client_drift(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        auth_headers: dict,
    ):
        proposal = await _make_proposal(db_session, test_user)

        resp = await client.post(
            f"/api/proposals/{proposal.id}/packages",
            json=_package_payload(),
            headers=auth_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["subtotal"] == "1000.00"
        assert data["discount_amount"] == "125.00"
        assert data["tax_amount"] == "0.00"
        assert data["total"] == "875.00"
        assert data["items"][0]["total"] == "875.00"

    async def test_invalid_package_payloads_are_rejected(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        auth_headers: dict,
    ):
        proposal = await _make_proposal(db_session, test_user)
        invalid = _package_payload(
            payment_type="subscription",
            recurring_interval=None,
            recurring_interval_count=None,
        )

        resp = await client.post(
            f"/api/proposals/{proposal.id}/packages",
            json=invalid,
            headers=auth_headers,
        )
        assert resp.status_code == 422

    async def test_package_mutation_is_draft_only(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        auth_headers: dict,
    ):
        proposal = await _make_proposal(db_session, test_user, status="sent")

        resp = await client.post(
            f"/api/proposals/{proposal.id}/packages",
            json=_package_payload(),
            headers=auth_headers,
        )
        assert resp.status_code == 400

    async def test_public_response_filters_inactive_and_internal_fields(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        proposal = await _make_proposal(db_session, test_user, status="sent")
        await _add_package(db_session, proposal, is_active=True, is_recommended=True)
        await _add_package(db_session, proposal, name="Hidden", is_active=False)

        resp = await client.get(f"/api/proposals/public/{proposal.public_token}")
        assert resp.status_code == 200
        data = resp.json()
        assert [pkg["name"] for pkg in data["packages"]] == ["Growth Package"]
        assert "product_id" not in data["packages"][0]["items"][0]
        assert "price_id" not in data["packages"][0]["items"][0]
        assert "created_by_id" not in data["packages"][0]

    async def test_public_payment_fields_null_when_packages_exist(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        proposal = await _make_proposal(
            db_session,
            test_user,
            status="awaiting_payment",
            amount=900,
            stripe_payment_url="https://pay.example.test/session",
        )
        await _add_package(db_session, proposal)

        resp = await client.get(f"/api/proposals/public/{proposal.public_token}")
        assert resp.status_code == 200
        data = resp.json()
        for field in (
            "payment_type",
            "recurring_interval",
            "recurring_interval_count",
            "amount",
            "currency",
            "stripe_payment_url",
            "paid_at",
        ):
            assert data[field] is None

    async def test_public_accept_requires_and_persists_selected_package(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        # No mocks — accept runs the real fail-soft stamp + send_signed_copy
        # paths. R2 is unconfigured in tests so the stamp path captures the
        # error onto signed_pdf_error (no exception leaks), and the email
        # send is itself fail-soft (logged-warning when no owner Gmail/SMTP).
        proposal = await _make_proposal(db_session, test_user, status="sent")
        package = await _add_package(db_session, proposal, is_recommended=True)
        signature = "data:image/png;base64," + base64.b64encode(_ONE_PIXEL_PNG).decode()

        missing = await client.post(
            f"/api/proposals/public/{proposal.public_token}/accept",
            json={
                "signer_name": "Signer",
                "signer_email": "signer@example.com",
                "signature_image": signature,
                "agreed_to_terms": True,
            },
        )
        assert missing.status_code == 400

        resp = await client.post(
            f"/api/proposals/public/{proposal.public_token}/accept",
            json={
                "signer_name": "Signer",
                "signer_email": "signer@example.com",
                "signature_image": signature,
                "agreed_to_terms": True,
                "selected_package_id": package.id,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["selected_package_snapshot"]["package_id"] == package.id
        assert data["selected_package_snapshot"]["total"] == "900.00"
        assert data["packages"] == []
        for field in ("payment_type", "amount", "currency", "stripe_payment_url"):
            assert data[field] is None

        await db_session.refresh(proposal)
        assert proposal.selected_package_id == package.id
        snapshot = proposal.selected_package_snapshot
        assert snapshot is not None
        assert snapshot["items"][0]["description"] == "Implementation"
        activity = (
            await db_session.execute(
                select(Activity).where(
                    Activity.entity_type == "proposals",
                    Activity.entity_id == proposal.id,
                    Activity.subject.like("Package selected:%"),
                )
            )
        ).scalar_one_or_none()
        assert activity is not None

    async def test_patch_package_updates_fields_and_recomputes_total(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        auth_headers: dict,
    ):
        proposal = await _make_proposal(db_session, test_user)
        package = await _add_package(db_session, proposal)
        await db_session.refresh(package, ["items"])

        resp = await client.patch(
            f"/api/proposals/{proposal.id}/packages/{package.id}",
            json={
                "name": "Renamed Package",
                "is_recommended": True,
                "items": [
                    {
                        "id": package.items[0].id,
                        "description": "Updated line",
                        "quantity": "3.00",
                        "unit_price": "200.00",
                        "discount_amount": "0.00",
                        "sort_order": 1,
                    }
                ],
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["name"] == "Renamed Package"
        assert data["is_recommended"] is True
        # Server recomputes; client-supplied subtotal/total are ignored.
        assert data["total"] == "600.00"
        assert data["items"][0]["description"] == "Updated line"

    async def test_delete_package_deactivates_then_allows_new_recommended(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        auth_headers: dict,
    ):
        """Regression: deleting a recommended package must not brick the
        recommendation slot for the proposal. Deactivating a recommended
        row drops it out of the partial unique index AND out of the
        application-layer recommendation guard so a new recommended
        package can be created."""
        proposal = await _make_proposal(db_session, test_user)
        original = await _add_package(db_session, proposal, is_recommended=True)

        # Delete is a soft-delete: row stays, is_active flips to False.
        delete_resp = await client.delete(
            f"/api/proposals/{proposal.id}/packages/{original.id}",
            headers=auth_headers,
        )
        assert delete_resp.status_code == 200
        assert delete_resp.json()["is_active"] is False

        # New recommended package must be allowed — the deactivated row
        # no longer competes for the "one recommended" slot.
        create_resp = await client.post(
            f"/api/proposals/{proposal.id}/packages",
            json=_package_payload(name="Replacement Recommended", is_recommended=True),
            headers=auth_headers,
        )
        assert create_resp.status_code == 201, create_resp.text
        assert create_resp.json()["is_recommended"] is True

    async def test_patch_package_blocks_second_active_recommended(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        auth_headers: dict,
    ):
        """The guard still kicks in for two ACTIVE recommended packages."""
        proposal = await _make_proposal(db_session, test_user)
        await _add_package(db_session, proposal, is_recommended=True)
        runner_up = await _add_package(db_session, proposal, name="Runner Up")

        resp = await client.patch(
            f"/api/proposals/{proposal.id}/packages/{runner_up.id}",
            json={"is_recommended": True},
            headers=auth_headers,
        )
        assert resp.status_code == 400

    async def test_legacy_billing_fields_remain_rejected_on_create_and_update(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        auth_headers: dict,
    ):
        create_resp = await client.post(
            "/api/proposals",
            json={
                "title": "No legacy billing writes",
                "amount": "100.00",
                "payment_type": "subscription",
            },
            headers=auth_headers,
        )
        assert create_resp.status_code == 422

        proposal = await _make_proposal(db_session, test_user)
        patch_resp = await client.patch(
            f"/api/proposals/{proposal.id}",
            json={"amount": "100.00"},
            headers=auth_headers,
        )
        assert patch_resp.status_code == 422
