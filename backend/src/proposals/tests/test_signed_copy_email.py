"""``ProposalService.send_signed_copy_to_client`` attachment selection.

The signer email needs to ship the legally-executed stamped PDF when
one is on file. If R2 hiccups, the email still goes out — but with the
HTML-derived ``generate_proposal_pdf`` copy so the signer is never left
with no attachment at all. When ``signed_pdf_path`` is null (e.g.
``master_contract_pdf_path`` was never uploaded), the generated copy is
the only option and is used unconditionally.

External boundaries are stubbed at module-import seams (per CLAUDE.md
"no mocks"): ``download_object_bytes`` for R2 and
``EmailService.queue_email`` for SMTP. The DB is the real SQLite
in-memory engine.
"""

from __future__ import annotations

import os
import secrets
import sys
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

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
from src.contacts.models import Contact  # noqa: F401
from src.contracts.models import Contract  # noqa: F401
from src.core.models import EntityShare, EntityTag, Note, Tag  # noqa: F401
from src.dashboard.models import (  # noqa: F401
    DashboardChart,
    DashboardNumberCard,
    DashboardReportWidget,
)
from src.database import Base
from src.email.models import EmailQueue, EmailSettings, InboundEmail  # noqa: F401
from src.email.service import EmailService
from src.email.types import EmailAttachment
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


async def _make_user(db: AsyncSession) -> User:
    user = User(
        email=f"sender-{secrets.token_hex(4)}@test.com",
        hashed_password=get_password_hash("password"),
        full_name="Owner",
        is_active=True,
        is_approved=True,
        is_superuser=True,
        role="admin",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _make_proposal(
    db: AsyncSession,
    owner: User,
    *,
    signed_pdf_path: str | None,
) -> Proposal:
    proposal = Proposal(
        proposal_number=f"PR-{secrets.token_hex(4).upper()}",
        title="Service Agreement",
        status="accepted",
        amount=1500.0,
        currency="USD",
        payment_type="one_time",
        owner_id=owner.id,
        created_by_id=owner.id,
        signed_at=datetime.now(UTC),
        signer_name="Customer Signer",
        signer_email="customer@example.com",
        signer_ip="203.0.113.7",
        signer_user_agent="Mozilla/5.0 TestUA",
        master_contract_pdf_path="proposals/9/master.pdf",
        signature_image=b"\x89PNG\r\n\x1a\n",
        signed_pdf_path=signed_pdf_path,
    )
    db.add(proposal)
    await db.commit()
    await db.refresh(proposal)
    return proposal


class _QueueRecorder:
    """Captures the kwargs passed to ``EmailService.queue_email`` so the
    test can assert on attachment filenames + bytes without exercising
    SMTP / Gmail / the throttle path."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def make_stub(self):
        recorder = self

        async def stub(self_es: EmailService, **kwargs):
            recorder.calls.append(kwargs)

        return stub


@pytest.fixture
def email_recorder(monkeypatch: pytest.MonkeyPatch) -> _QueueRecorder:
    recorder = _QueueRecorder()
    monkeypatch.setattr(
        EmailService, "queue_email", recorder.make_stub(), raising=True
    )
    return recorder


class TestSendSignedCopyToClient:

    async def test_attaches_stamped_pdf_when_signed_pdf_path_set(
        self,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
        email_recorder: _QueueRecorder,
    ):
        user = await _make_user(db_session)
        proposal = await _make_proposal(
            db_session, user, signed_pdf_path="proposals/9/signed.pdf"
        )
        stamped_bytes = b"%PDF-1.7\nSTAMPED MASTER COPY"

        async def fake_download(key: str) -> bytes:
            assert key == "proposals/9/signed.pdf"
            return stamped_bytes

        # service.py imports download_object_bytes at module top, so the
        # in-function reference resolves to the module-level binding.
        monkeypatch.setattr(
            "src.proposals.service.download_object_bytes", fake_download
        )

        async def fail_generate(*args, **kwargs):
            raise AssertionError(
                "generate_proposal_pdf must not run when stamped PDF is "
                "available — the legally-executed copy is what the "
                "signer expects to receive."
            )

        monkeypatch.setattr(
            ProposalService, "generate_proposal_pdf", fail_generate
        )

        service = ProposalService(db_session)
        await service.send_signed_copy_to_client(proposal)

        assert len(email_recorder.calls) == 1
        call = email_recorder.calls[0]
        assert call["to_email"] == "customer@example.com"
        attachments: list[EmailAttachment] = call["attachments"]
        assert len(attachments) == 1
        assert attachments[0]["filename"] == (
            f"proposal-{proposal.proposal_number}-signed.pdf"
        )
        assert attachments[0]["content"] == stamped_bytes
        assert attachments[0]["content_type"] == "application/pdf"

    async def test_falls_back_to_generated_pdf_on_r2_failure(
        self,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
        email_recorder: _QueueRecorder,
    ):
        user = await _make_user(db_session)
        proposal = await _make_proposal(
            db_session, user, signed_pdf_path="proposals/9/signed.pdf"
        )

        async def fake_download(key: str) -> bytes:
            raise RuntimeError("R2 unreachable")

        monkeypatch.setattr(
            "src.proposals.service.download_object_bytes", fake_download
        )

        generated_bytes = b"%PDF-1.7\nGENERATED FALLBACK"

        async def fake_generate(self, proposal_id, user_id, include_signature=False):
            assert proposal_id == proposal.id
            assert include_signature is True
            return generated_bytes

        monkeypatch.setattr(
            ProposalService, "generate_proposal_pdf", fake_generate
        )

        service = ProposalService(db_session)
        await service.send_signed_copy_to_client(proposal)

        assert len(email_recorder.calls) == 1
        call = email_recorder.calls[0]
        attachments: list[EmailAttachment] = call["attachments"]
        assert len(attachments) == 1
        assert attachments[0]["filename"] == (
            f"proposal-{proposal.proposal_number}-signed.pdf"
        )
        assert attachments[0]["content"] == generated_bytes

    async def test_uses_generated_pdf_when_signed_pdf_path_null(
        self,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
        email_recorder: _QueueRecorder,
    ):
        user = await _make_user(db_session)
        proposal = await _make_proposal(
            db_session, user, signed_pdf_path=None
        )

        async def fail_download(*args, **kwargs):
            raise AssertionError(
                "download_object_bytes must not be called when "
                "signed_pdf_path is null — there is no R2 key to fetch."
            )

        monkeypatch.setattr(
            "src.proposals.service.download_object_bytes", fail_download
        )

        generated_bytes = b"%PDF-1.7\nHTML-DERIVED COPY"

        async def fake_generate(self, proposal_id, user_id, include_signature=False):
            assert proposal_id == proposal.id
            assert include_signature is True
            return generated_bytes

        monkeypatch.setattr(
            ProposalService, "generate_proposal_pdf", fake_generate
        )

        service = ProposalService(db_session)
        await service.send_signed_copy_to_client(proposal)

        assert len(email_recorder.calls) == 1
        call = email_recorder.calls[0]
        attachments: list[EmailAttachment] = call["attachments"]
        assert len(attachments) == 1
        assert attachments[0]["filename"] == (
            f"proposal-{proposal.proposal_number}-signed.pdf"
        )
        assert attachments[0]["content"] == generated_bytes
