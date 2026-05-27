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

    async def test_per_sibling_rejection_activity_row_is_logged(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        # The winner's Activity is covered above; this verifies HIGH #5 — the
        # owner's timeline shows every option that flipped to rejected too,
        # not just the one that was accepted.
        winner = await _make_proposal(db_session, test_user, title="Winner", status="sent")
        loser_a = await _make_proposal(db_session, test_user, title="Loser A", status="sent")
        loser_b = await _make_proposal(db_session, test_user, title="Loser B", status="sent")
        await _make_bundle(db_session, test_user, [winner, loser_a, loser_b], status="sent")
        signature = "data:image/png;base64," + base64.b64encode(_ONE_PIXEL_PNG).decode()

        resp = await client.post(
            f"/api/proposals/public/{winner.public_token}/accept",
            json={
                "signer_name": "Signer",
                "signer_email": "signer@example.com",
                "signature_image": signature,
                "agreed_to_terms": True,
                "selected_proposal_id": winner.id,
            },
        )
        assert resp.status_code == 200

        rejection_activities = (
            await db_session.execute(
                select(Activity).where(
                    Activity.entity_type == "proposals",
                    Activity.entity_id.in_([loser_a.id, loser_b.id]),
                    Activity.subject.like("Proposal rejected:%"),
                )
            )
        ).scalars().all()
        rejected_entity_ids = {a.entity_id for a in rejection_activities}
        assert rejected_entity_ids == {loser_a.id, loser_b.id}, (
            "Expected an Activity row for every sibling flipped to rejected"
        )

    async def test_second_accept_attempt_blocks_after_first_wins(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        # CRITICAL #1 — after one sibling is accepted, attempting to accept
        # another in the same bundle must fail (400 from value_error_as_400).
        # The DB-level partial unique index is the prod backstop; this test
        # validates the app-layer guard that fires first.
        first = await _make_proposal(db_session, test_user, title="First", status="sent")
        second = await _make_proposal(db_session, test_user, title="Second", status="sent")
        await _make_bundle(db_session, test_user, [first, second], status="sent")
        signature = "data:image/png;base64," + base64.b64encode(_ONE_PIXEL_PNG).decode()

        first_resp = await client.post(
            f"/api/proposals/public/{first.public_token}/accept",
            json={
                "signer_name": "Signer",
                "signer_email": "signer@example.com",
                "signature_image": signature,
                "agreed_to_terms": True,
                "selected_proposal_id": first.id,
            },
        )
        assert first_resp.status_code == 200

        # Second sibling: its per-proposal status check would already reject
        # this, but more importantly the bundle-FOR-UPDATE path means even
        # if the per-proposal check were bypassed (different transaction
        # ordering, race), the bundle.status='accepted' guard refuses.
        second_resp = await client.post(
            f"/api/proposals/public/{second.public_token}/accept",
            json={
                "signer_name": "Signer",
                "signer_email": "signer@example.com",
                "signature_image": signature,
                "agreed_to_terms": True,
                "selected_proposal_id": second.id,
            },
        )
        assert second_resp.status_code == 400

    async def test_accept_with_bundle_token_returns_400_pick_option(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        # HIGH #6 — bundle token sent to the per-proposal accept endpoint
        # used to return a generic 404. Resolve as bundle first; if no
        # selection has been made, return 400 with an actionable message.
        first = await _make_proposal(db_session, test_user, title="Lean", status="sent")
        second = await _make_proposal(db_session, test_user, title="Full", status="sent")
        bundle = await _make_bundle(db_session, test_user, [first, second], status="sent")
        signature = "data:image/png;base64," + base64.b64encode(_ONE_PIXEL_PNG).decode()

        resp = await client.post(
            f"/api/proposals/public/{bundle.public_token}/accept",
            json={
                "signer_name": "Signer",
                "signer_email": "signer@example.com",
                "signature_image": signature,
                "agreed_to_terms": True,
            },
        )
        assert resp.status_code == 400
        assert "pick" in resp.json()["detail"].lower()

    async def test_accept_with_bundle_token_returns_409_after_selection(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        # HIGH #6 — once the bundle has been selected, a stale bundle-token
        # accept returns 409, not 404.
        first = await _make_proposal(db_session, test_user, title="Lean", status="sent")
        second = await _make_proposal(db_session, test_user, title="Full", status="sent")
        bundle = await _make_bundle(db_session, test_user, [first, second], status="sent")
        signature = "data:image/png;base64," + base64.b64encode(_ONE_PIXEL_PNG).decode()

        first_resp = await client.post(
            f"/api/proposals/public/{first.public_token}/accept",
            json={
                "signer_name": "Signer",
                "signer_email": "signer@example.com",
                "signature_image": signature,
                "agreed_to_terms": True,
                "selected_proposal_id": first.id,
            },
        )
        assert first_resp.status_code == 200

        bundle_resp = await client.post(
            f"/api/proposals/public/{bundle.public_token}/accept",
            json={
                "signer_name": "Signer",
                "signer_email": "signer@example.com",
                "signature_image": signature,
                "agreed_to_terms": True,
            },
        )
        assert bundle_resp.status_code == 409
        assert "already accepted" in bundle_resp.json()["detail"].lower()

    async def test_record_bundle_view_does_not_rearm_accepted_bundle(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        # HIGH #3 — opening the bundle URL after acceptance must not flip
        # any leftover sent sibling back to viewed (which would widen the
        # accept race in #1).
        first = await _make_proposal(db_session, test_user, title="A", status="sent")
        second = await _make_proposal(db_session, test_user, title="B", status="sent")
        bundle = await _make_bundle(db_session, test_user, [first, second], status="sent")
        signature = "data:image/png;base64," + base64.b64encode(_ONE_PIXEL_PNG).decode()

        await client.post(
            f"/api/proposals/public/{first.public_token}/accept",
            json={
                "signer_name": "Signer",
                "signer_email": "signer@example.com",
                "signature_image": signature,
                "agreed_to_terms": True,
                "selected_proposal_id": first.id,
            },
        )

        # GET on the bundle token after accept — this calls record_bundle_view.
        resp = await client.get(f"/api/proposals/public/{bundle.public_token}")
        assert resp.status_code == 200

        await db_session.refresh(first)
        await db_session.refresh(second)
        await db_session.refresh(bundle)
        assert first.status == "accepted"
        assert second.status == "rejected", (
            "Rejected sibling must NOT be re-armed to viewed by record_bundle_view"
        )
        assert bundle.status == "accepted"

    async def test_proposal_model_has_accepted_selection_snapshot_column(self):
        # CRITICAL #2 — migration 047 backfills PR #378's signed snapshots
        # into this column. The model must declare it so the ORM can read
        # the preserved audit data.
        cols = Base.metadata.tables["proposals"].c
        assert "accepted_selection_snapshot" in cols

    # ------------------------------------------------------------------
    # Bundle refinement: list hides sub-options, recommend toggle, remove
    # option, dissolve-on-1-survivor.
    # ------------------------------------------------------------------

    async def test_list_proposals_hides_bundle_sub_options(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        auth_headers: dict,
    ):
        """The list endpoint must show the bundle's primary proposal only —
        sub-options (sort_order > 0) live inside the parent's detail page.
        """
        standalone = await _make_proposal(db_session, test_user, title="Solo")
        primary = await _make_proposal(db_session, test_user, title="Primary")
        sub = await _make_proposal(db_session, test_user, title="Sub")
        await _make_bundle(db_session, test_user, [primary, sub])

        resp = await client.get("/api/proposals", headers=auth_headers)
        assert resp.status_code == 200
        ids = {item["id"] for item in resp.json()["items"]}
        assert standalone.id in ids
        assert primary.id in ids, "Bundle primary (sort_order=0) must surface"
        assert sub.id not in ids, "Sub-option (sort_order>0) must be hidden"

    async def test_patch_bundle_recommendation_to_specific_proposal(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        auth_headers: dict,
    ):
        first = await _make_proposal(db_session, test_user, title="First")
        second = await _make_proposal(db_session, test_user, title="Second")
        bundle = await _make_bundle(db_session, test_user, [first, second])

        resp = await client.patch(
            f"/api/proposals/bundles/{bundle.id}",
            headers=auth_headers,
            json={"recommended_proposal_id": second.id},
        )
        assert resp.status_code == 200
        await db_session.refresh(first)
        await db_session.refresh(second)
        assert first.bundle_is_recommended is False
        assert second.bundle_is_recommended is True

    async def test_patch_bundle_recommendation_null_clears_all(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        auth_headers: dict,
    ):
        first = await _make_proposal(db_session, test_user, title="A")
        second = await _make_proposal(db_session, test_user, title="B")
        bundle = await _make_bundle(db_session, test_user, [first, second])
        # Sanity: _make_bundle defaults the index==0 row to recommended.
        await db_session.refresh(first)
        assert first.bundle_is_recommended is True

        resp = await client.patch(
            f"/api/proposals/bundles/{bundle.id}",
            headers=auth_headers,
            json={"recommended_proposal_id": None},
        )
        assert resp.status_code == 200
        await db_session.refresh(first)
        await db_session.refresh(second)
        assert first.bundle_is_recommended is False
        assert second.bundle_is_recommended is False

    async def test_patch_bundle_rejects_recommendation_for_non_member(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        auth_headers: dict,
    ):
        first = await _make_proposal(db_session, test_user, title="A")
        second = await _make_proposal(db_session, test_user, title="B")
        outsider = await _make_proposal(db_session, test_user, title="Outsider")
        bundle = await _make_bundle(db_session, test_user, [first, second])

        resp = await client.patch(
            f"/api/proposals/bundles/{bundle.id}",
            headers=auth_headers,
            json={"recommended_proposal_id": outsider.id},
        )
        assert resp.status_code == 400

    async def test_patch_combined_payload_adds_and_recommends_new_member(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        auth_headers: dict,
    ):
        """Regression for the audit P1: a combined PATCH that adds C to
        the bundle AND marks C as recommended must succeed — the
        recommendation check has to consult the NEW membership, not the
        stale bundle.proposals relationship that still reflects [A, B].
        """
        a = await _make_proposal(db_session, test_user, title="A")
        b = await _make_proposal(db_session, test_user, title="B")
        c = await _make_proposal(db_session, test_user, title="C")
        bundle = await _make_bundle(db_session, test_user, [a, b])

        resp = await client.patch(
            f"/api/proposals/bundles/{bundle.id}",
            headers=auth_headers,
            json={
                "proposal_ids": [a.id, b.id, c.id],
                "recommended_proposal_id": c.id,
            },
        )
        assert resp.status_code == 200, resp.text
        await db_session.refresh(c)
        assert c.bundle_is_recommended is True
        await db_session.refresh(a)
        await db_session.refresh(b)
        assert a.bundle_is_recommended is False
        assert b.bundle_is_recommended is False

    async def test_patch_combined_payload_cannot_recommend_removed_member(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        auth_headers: dict,
    ):
        """Regression for the audit P1: removing C from the bundle AND
        recommending C in the same PATCH must be rejected — and C must
        end up unbundled with `bundle_is_recommended=False`, NOT a
        standalone proposal still flagged as recommended.
        """
        a = await _make_proposal(db_session, test_user, title="A")
        b = await _make_proposal(db_session, test_user, title="B")
        c = await _make_proposal(db_session, test_user, title="C")
        bundle = await _make_bundle(db_session, test_user, [a, b, c])

        resp = await client.patch(
            f"/api/proposals/bundles/{bundle.id}",
            headers=auth_headers,
            json={
                "proposal_ids": [a.id, b.id],
                "recommended_proposal_id": c.id,
            },
        )
        assert resp.status_code == 400
        await db_session.refresh(c)
        # The atomic-PATCH guarantee: 400 means the whole transaction
        # rolled back; C is still a bundle member with its prior state.
        # (Without `for_update` row-locking + the membership check, the
        # bug surfaced as: C unbundled AND marked recommended.)
        assert c.proposal_bundle_id == bundle.id, (
            "PATCH rollback must keep C bundled when the request is rejected"
        )
        assert c.bundle_is_recommended is False

    async def test_patch_proposal_ids_preserves_user_recommendation(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        auth_headers: dict,
    ):
        """If the user marked option B as recommended and then 'Add option'
        appends C, B must stay recommended — must NOT snap back to index==0.
        Regression of the pre-refinement behavior.
        """
        a = await _make_proposal(db_session, test_user, title="A")
        b = await _make_proposal(db_session, test_user, title="B")
        c = await _make_proposal(db_session, test_user, title="C")
        bundle = await _make_bundle(db_session, test_user, [a, b])

        # User flips recommended → B.
        resp = await client.patch(
            f"/api/proposals/bundles/{bundle.id}",
            headers=auth_headers,
            json={"recommended_proposal_id": b.id},
        )
        assert resp.status_code == 200

        # User adds C; recommendation should remain on B.
        resp = await client.patch(
            f"/api/proposals/bundles/{bundle.id}",
            headers=auth_headers,
            json={"proposal_ids": [a.id, b.id, c.id]},
        )
        assert resp.status_code == 200
        await db_session.refresh(a)
        await db_session.refresh(b)
        await db_session.refresh(c)
        assert a.bundle_is_recommended is False
        assert b.bundle_is_recommended is True, (
            "Recommendation must survive proposal_ids changes that keep B"
        )
        assert c.bundle_is_recommended is False

    async def test_remove_option_endpoint_shrinks_bundle(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        auth_headers: dict,
    ):
        a = await _make_proposal(db_session, test_user, title="A")
        b = await _make_proposal(db_session, test_user, title="B")
        c = await _make_proposal(db_session, test_user, title="C")
        bundle = await _make_bundle(db_session, test_user, [a, b, c])

        resp = await client.delete(
            f"/api/proposals/bundles/{bundle.id}/options/{b.id}",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert [p["id"] for p in data["proposals"]] == [a.id, c.id]
        await db_session.refresh(b)
        assert b.proposal_bundle_id is None
        assert b.bundle_is_recommended is False

    async def test_remove_option_dissolves_when_one_survivor(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        auth_headers: dict,
    ):
        """Removing one option from a 2-bundle dissolves the bundle: the
        survivor goes back to being a standalone draft and the bundle row
        is deleted. The endpoint returns 204.
        """
        a = await _make_proposal(db_session, test_user, title="A")
        b = await _make_proposal(db_session, test_user, title="B")
        bundle = await _make_bundle(db_session, test_user, [a, b])
        bundle_id = bundle.id

        resp = await client.delete(
            f"/api/proposals/bundles/{bundle_id}/options/{b.id}",
            headers=auth_headers,
        )
        assert resp.status_code == 204

        await db_session.refresh(a)
        await db_session.refresh(b)
        assert a.proposal_bundle_id is None
        assert a.bundle_is_recommended is False
        assert b.proposal_bundle_id is None

        gone = (
            await db_session.execute(
                select(ProposalBundle).where(ProposalBundle.id == bundle_id)
            )
        ).scalar_one_or_none()
        assert gone is None, "Dissolved bundle must be deleted"

    async def test_remove_option_404_when_proposal_not_in_bundle(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        auth_headers: dict,
    ):
        a = await _make_proposal(db_session, test_user, title="A")
        b = await _make_proposal(db_session, test_user, title="B")
        outsider = await _make_proposal(db_session, test_user, title="Outsider")
        bundle = await _make_bundle(db_session, test_user, [a, b])

        resp = await client.delete(
            f"/api/proposals/bundles/{bundle.id}/options/{outsider.id}",
            headers=auth_headers,
        )
        assert resp.status_code == 400

    async def test_remove_option_blocked_when_bundle_not_draft(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        auth_headers: dict,
    ):
        a = await _make_proposal(db_session, test_user, title="A")
        b = await _make_proposal(db_session, test_user, title="B")
        bundle = await _make_bundle(db_session, test_user, [a, b], status="sent")

        resp = await client.delete(
            f"/api/proposals/bundles/{bundle.id}/options/{b.id}",
            headers=auth_headers,
        )
        assert resp.status_code == 400

    async def test_delete_bundled_proposal_removes_from_bundle(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        auth_headers: dict,
    ):
        """Deleting a bundled proposal via DELETE /proposals/{id} must route
        through remove_option_from_bundle so the surviving options keep
        consistent sort_order and the bundle dissolves when ≤1 remains."""
        a = await _make_proposal(db_session, test_user, title="Primary")
        b = await _make_proposal(db_session, test_user, title="Secondary")
        c = await _make_proposal(db_session, test_user, title="Tertiary")
        bundle = await _make_bundle(db_session, test_user, [a, b, c])

        resp = await client.delete(
            f"/api/proposals/{b.id}", headers=auth_headers,
        )
        assert resp.status_code == 204

        db_session.expire_all()
        remaining = (await db_session.execute(
            select(Proposal)
            .where(Proposal.proposal_bundle_id == bundle.id)
            .order_by(Proposal.bundle_sort_order)
        )).scalars().all()
        assert len(remaining) == 2
        assert [p.id for p in remaining] == [a.id, c.id]
        assert remaining[0].bundle_sort_order == 0
        assert remaining[1].bundle_sort_order == 1

    async def test_delete_primary_bundled_proposal_dissolves_2_option_bundle(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        auth_headers: dict,
    ):
        """Deleting the primary (sort_order=0) proposal from a 2-option
        bundle should dissolve the bundle, leaving the survivor standalone."""
        a = await _make_proposal(db_session, test_user, title="Primary")
        b = await _make_proposal(db_session, test_user, title="Secondary")
        bundle = await _make_bundle(db_session, test_user, [a, b])
        bundle_id = bundle.id

        resp = await client.delete(
            f"/api/proposals/{a.id}", headers=auth_headers,
        )
        assert resp.status_code == 204

        db_session.expire_all()
        survivor = await db_session.get(Proposal, b.id)
        assert survivor is not None
        assert survivor.proposal_bundle_id is None
        assert survivor.bundle_sort_order == 0
        bundle_row = await db_session.get(ProposalBundle, bundle_id)
        assert bundle_row is None

    async def test_search_matches_sub_option_surfaces_parent(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        auth_headers: dict,
    ):
        """Searching for a sub-option's title should surface the parent bundle
        row (sort_order=0) in the list even though sub-options are hidden."""
        parent = await _make_proposal(db_session, test_user, title="Main Offer")
        child = await _make_proposal(db_session, test_user, title="Premium Upgrade")
        await _make_bundle(db_session, test_user, [parent, child])

        resp = await client.get(
            "/api/proposals", params={"search": "Premium"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        titles = [p["title"] for p in resp.json()["items"]]
        assert "Main Offer" in titles

    async def test_bundle_lock_select_uses_of_proposal_bundles(self):
        """Regression: bare `with_for_update()` on `select(ProposalBundle)`
        raised asyncpg ``FeatureNotSupportedError: FOR UPDATE cannot be
        applied to the nullable side of an outer join`` in prod because
        ProposalBundle declares five `lazy="joined"` relations
        (contact, company, owner, created_by_user, selected_proposal)
        that emit LEFT OUTER JOINs in the primary SELECT.

        SQLite ignores FOR UPDATE entirely so this can't reproduce the
        PG runtime error directly. Instead we compile the *actual*
        statement produced by ProposalService._bundle_lock_select with
        the PG dialect and assert the lock is scoped to the bundle
        table. Reverting `_bundle_lock_select` to bare
        `with_for_update()` makes this fail.
        """
        from sqlalchemy.dialects import postgresql

        from src.proposals.service import ProposalService

        stmt = ProposalService._bundle_lock_select(1)
        sql = str(stmt.compile(dialect=postgresql.dialect()))
        assert "FOR UPDATE OF proposal_bundles" in sql, sql
