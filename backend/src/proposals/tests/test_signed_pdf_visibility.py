"""Restamp guards + endpoint surface.

Assumes R2 is unconfigured in the test env; if that changes,
``TestRestampCapturesFailure`` needs an explicit boto stub to keep
exercising the capture path instead of silently flipping to success.
"""

from __future__ import annotations

import os
import secrets
import sys
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from botocore.exceptions import ClientError
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
from src.proposals.service import ProposalService
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


class _Unset:
    """Sentinel so callers can pass explicit ``None`` without the
    default-when-missing logic overriding it."""


_UNSET = _Unset()


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


@pytest_asyncio.fixture(autouse=True)
def _clear_user_cache():
    # The module-level TTLCache in src.auth.dependencies survives across
    # test modules. Each test file uses its own in-memory DB but the
    # user-id keys collide, so a superuser cached from a sibling test's
    # auth would silently authorize this file's "intruder" — clear it.
    from src.auth.dependencies import _user_cache

    _user_cache.clear()
    yield
    _user_cache.clear()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession, test_engine) -> AsyncGenerator[AsyncClient, None]:
    from src.main import app

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def _make_user(
    db_session: AsyncSession,
    *,
    is_superuser: bool = True,
    role: str = "admin",
) -> User:
    user = User(
        email=f"user-{secrets.token_hex(4)}@test.com",
        hashed_password=get_password_hash("password"),
        full_name="Test User",
        is_active=True,
        is_approved=True,
        is_superuser=is_superuser,
        role=role,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


def _auth_headers(user: User) -> dict:
    token = create_access_token({"sub": str(user.id)})
    return {"Authorization": f"Bearer {token}"}


async def _make_proposal(
    db: AsyncSession,
    owner: User,
    *,
    status: str = "accepted",
    master_contract_pdf_path: str | None = "proposals/9/master.pdf",
    signature_image: bytes | None = b"\x89PNG\r\n\x1a\n",
    signed_at: datetime | None | _Unset = _UNSET,
    signed_pdf_error: str | None = None,
) -> Proposal:
    if isinstance(signed_at, _Unset):
        signed_at = datetime.now(UTC) if status != "draft" else None
    proposal = Proposal(
        proposal_number=f"PR-{secrets.token_hex(4).upper()}",
        title="Restamp Test",
        status=status,
        amount=500.0,
        currency="USD",
        payment_type="one_time",
        owner_id=owner.id,
        created_by_id=owner.id,
        signed_at=signed_at,
        signer_name="Customer Signer",
        signer_email="customer@example.com",
        signer_ip="203.0.113.7",
        signer_user_agent="Mozilla/5.0 TestUA",
        master_contract_pdf_path=master_contract_pdf_path,
        signature_image=signature_image,
        signed_pdf_error=signed_pdf_error,
    )
    db.add(proposal)
    await db.commit()
    await db.refresh(proposal)
    return proposal


class TestRestampServiceGuards:

    async def test_rejects_when_no_master_contract_pdf(
        self, db_session: AsyncSession
    ):
        user = await _make_user(db_session)
        proposal = await _make_proposal(
            db_session, user, master_contract_pdf_path=None
        )
        service = ProposalService(db_session)
        with pytest.raises(ValueError, match="signing document PDF"):
            await service.restamp_signed_pdf(proposal)

    async def test_rejects_when_no_signature_image(
        self, db_session: AsyncSession
    ):
        user = await _make_user(db_session)
        proposal = await _make_proposal(
            db_session, user, signature_image=None
        )
        service = ProposalService(db_session)
        with pytest.raises(ValueError, match="signature image"):
            await service.restamp_signed_pdf(proposal)

    @pytest.mark.parametrize("status", ["draft", "sent", "viewed", "rejected"])
    async def test_rejects_when_status_not_signed(
        self, db_session: AsyncSession, status: str
    ):
        user = await _make_user(db_session)
        proposal = await _make_proposal(db_session, user, status=status)
        service = ProposalService(db_session)
        with pytest.raises(ValueError, match="signed proposals"):
            await service.restamp_signed_pdf(proposal)

    async def test_rejects_when_no_signed_at(
        self, db_session: AsyncSession
    ):
        user = await _make_user(db_session)
        proposal = await _make_proposal(db_session, user, signed_at=None)
        service = ProposalService(db_session)
        with pytest.raises(ValueError, match="signed_at"):
            await service.restamp_signed_pdf(proposal)


class TestRestampCapturesFailure:
    """The accept-time stamper is fail-soft; restamp triggers the same
    fail-soft path, so a failure here should land on signed_pdf_error
    (not raise) AND the endpoint should still surface it loudly."""

    async def test_failure_populates_signed_pdf_error(
        self, db_session: AsyncSession
    ):
        user = await _make_user(db_session)
        proposal = await _make_proposal(db_session, user)
        service = ProposalService(db_session)

        # R2 not configured in the test env, so download_object_bytes
        # raises — we expect that to be caught + captured.
        result = await service.restamp_signed_pdf(proposal)
        assert result.signed_pdf_path is None
        assert result.signed_pdf_error is not None
        assert len(result.signed_pdf_error) <= 1000


class TestRestampEndpoint:

    async def test_endpoint_403_for_non_owner(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        owner = await _make_user(db_session, is_superuser=False, role="sales_rep")
        intruder = await _make_user(
            db_session, is_superuser=False, role="sales_rep"
        )
        proposal = await _make_proposal(db_session, owner)

        resp = await client.post(
            f"/api/proposals/{proposal.id}/restamp",
            headers=_auth_headers(intruder),
        )
        assert resp.status_code == 403

    async def test_endpoint_200_with_error_body_when_stamp_still_fails(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """200 + error-on-body keeps the row update in the DB.

        Raising HTTPException would propagate past ``get_db``'s
        narrow ``(OSError, SQLAlchemyError)`` handler and roll back
        the new ``signed_pdf_error`` write — defeating the whole
        point of this PR.
        """
        user = await _make_user(db_session)
        proposal = await _make_proposal(
            db_session, user, signed_pdf_error="Object storage unavailable: prior"
        )

        resp = await client.post(
            f"/api/proposals/{proposal.id}/restamp",
            headers=_auth_headers(user),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["signed_pdf_error"]
        assert body["signed_pdf_path"] is None

        await db_session.refresh(proposal)
        assert proposal.signed_pdf_path is None
        assert proposal.signed_pdf_error is not None

    async def test_endpoint_400_when_master_pdf_missing(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await _make_user(db_session)
        proposal = await _make_proposal(
            db_session, user, master_contract_pdf_path=None
        )

        resp = await client.post(
            f"/api/proposals/{proposal.id}/restamp",
            headers=_auth_headers(user),
        )
        assert resp.status_code == 400


class TestSignedPdfDownload:
    """``GET /api/proposals/{id}/signed-pdf`` failure mapping.

    Mirrors ``download_master_contract``'s R2 error contract:
    * 404 when ``signed_pdf_path`` is null or the R2 object is gone.
    * 503 on transient R2 / unexpected failures.
    * 200 + ``application/pdf`` body on the happy path.

    The endpoint imports ``download_object_bytes`` inside the function
    body, so patching the module attribute on
    ``src.attachments.object_storage`` is what actually takes effect.
    """

    async def test_returns_404_when_signed_pdf_path_null(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await _make_user(db_session)
        proposal = await _make_proposal(db_session, user)
        assert proposal.signed_pdf_path is None

        resp = await client.get(
            f"/api/proposals/{proposal.id}/signed-pdf",
            headers=_auth_headers(user),
        )
        assert resp.status_code == 404
        assert "No signed PDF on file" in resp.json().get("detail", "")

    async def test_returns_pdf_bytes_on_happy_path(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ):
        user = await _make_user(db_session)
        proposal = await _make_proposal(db_session, user)
        proposal.signed_pdf_path = "proposals/9/signed.pdf"
        await db_session.commit()

        expected = b"%PDF-1.7\n...signed bytes..."

        async def fake_download(key: str) -> bytes:
            assert key == "proposals/9/signed.pdf"
            return expected

        monkeypatch.setattr(
            "src.attachments.object_storage.download_object_bytes",
            fake_download,
        )

        resp = await client.get(
            f"/api/proposals/{proposal.id}/signed-pdf",
            headers=_auth_headers(user),
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert resp.content == expected

    @pytest.mark.parametrize("r2_code", ["NoSuchKey", "404", "NotFound"])
    async def test_returns_404_when_r2_object_missing(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
        r2_code: str,
    ):
        user = await _make_user(db_session)
        proposal = await _make_proposal(db_session, user)
        proposal.signed_pdf_path = "proposals/9/missing.pdf"
        await db_session.commit()

        async def fake_download(key: str) -> bytes:
            raise ClientError(
                {"Error": {"Code": r2_code, "Message": "gone"}},
                "GetObject",
            )

        monkeypatch.setattr(
            "src.attachments.object_storage.download_object_bytes",
            fake_download,
        )

        resp = await client.get(
            f"/api/proposals/{proposal.id}/signed-pdf",
            headers=_auth_headers(user),
        )
        assert resp.status_code == 404
        assert "re-stamp" in resp.json().get("detail", "").lower()

    async def test_returns_503_on_other_client_error(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ):
        user = await _make_user(db_session)
        proposal = await _make_proposal(db_session, user)
        proposal.signed_pdf_path = "proposals/9/signed.pdf"
        await db_session.commit()

        async def fake_download(key: str) -> bytes:
            raise ClientError(
                {"Error": {"Code": "InternalError", "Message": "boom"}},
                "GetObject",
            )

        monkeypatch.setattr(
            "src.attachments.object_storage.download_object_bytes",
            fake_download,
        )

        resp = await client.get(
            f"/api/proposals/{proposal.id}/signed-pdf",
            headers=_auth_headers(user),
        )
        assert resp.status_code == 503

    async def test_returns_503_on_unexpected_exception(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ):
        user = await _make_user(db_session)
        proposal = await _make_proposal(db_session, user)
        proposal.signed_pdf_path = "proposals/9/signed.pdf"
        await db_session.commit()

        async def fake_download(key: str) -> bytes:
            raise RuntimeError("network kaput")

        monkeypatch.setattr(
            "src.attachments.object_storage.download_object_bytes",
            fake_download,
        )

        resp = await client.get(
            f"/api/proposals/{proposal.id}/signed-pdf",
            headers=_auth_headers(user),
        )
        assert resp.status_code == 503

    async def test_endpoint_403_for_non_owner(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        owner = await _make_user(
            db_session, is_superuser=False, role="sales_rep"
        )
        intruder = await _make_user(
            db_session, is_superuser=False, role="sales_rep"
        )
        proposal = await _make_proposal(db_session, owner)
        proposal.signed_pdf_path = "proposals/9/signed.pdf"
        await db_session.commit()

        resp = await client.get(
            f"/api/proposals/{proposal.id}/signed-pdf",
            headers=_auth_headers(intruder),
        )
        assert resp.status_code == 403
