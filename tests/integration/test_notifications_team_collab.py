"""Integration tests for team-collab notification fan-out.

Covers:
- POST /api/sharing with permission_level='view'  → entity_shared_with_you notification
- POST /api/sharing with permission_level='assignee' → record_assigned_to_you notification
- POST /api/proposals/public/{token}/accept (non-owner signer) → proposal_signed notification to owner
- POST /api/contracts/public/{token}/sign (non-owner signer) → contract_signed notification to owner

All tests use the real SQLite in-memory DB (via conftest fixtures). No mocks.
"""

import secrets
from base64 import b64encode

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.account.models import UserNotificationPrefs
from src.auth.models import User
from src.auth.security import create_access_token, get_password_hash
from src.companies.models import Company
from src.contacts.models import Contact
from src.leads.models import Lead
from src.notifications.models import Notification
from src.opportunities.models import Opportunity, PipelineStage
from src.proposals.models import Proposal

# Smallest valid PNG (1x1 transparent) — the Sign-to-Confirm payload
# requires a drawn-signature image.
_ONE_PIXEL_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000d49444154789c63000000000005000158a8c4d70000000049454e44ae426082"
)
_SIG = "data:image/png;base64," + b64encode(_ONE_PIXEL_PNG).decode("ascii")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _make_user(db: AsyncSession, email: str, full_name: str = "Test Person") -> User:
    user = User(
        email=email,
        hashed_password=get_password_hash("password123"),
        full_name=full_name,
        is_active=True,
        is_superuser=True,  # superuser so sharing endpoint doesn't 403
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


def _headers(user: User) -> dict:
    token = create_access_token(data={"sub": str(user.id)})
    return {"Authorization": f"Bearer {token}"}


async def _make_contact(db: AsyncSession, owner: User, name: str = "Sample Contact") -> Contact:
    contact = Contact(
        first_name=name.split()[0],
        last_name=name.split()[-1] if " " in name else "Sample",
        owner_id=owner.id,
        created_by_id=owner.id,
    )
    db.add(contact)
    await db.commit()
    await db.refresh(contact)
    return contact


async def _make_lead(db: AsyncSession, owner: User, name: str = "Sample Lead") -> Lead:
    lead = Lead(
        first_name=name.split()[0],
        last_name=name.split()[-1] if " " in name else "Sample",
        owner_id=owner.id,
        created_by_id=owner.id,
    )
    db.add(lead)
    await db.commit()
    await db.refresh(lead)
    return lead


async def _make_opportunity(
    db: AsyncSession, owner: User, name: str = "Sample Opp"
) -> Opportunity:
    stage = PipelineStage(
        name="New",
        order=1,
        color="#06b6d4",
        probability=10,
        pipeline_type="opportunity",
    )
    db.add(stage)
    await db.commit()
    await db.refresh(stage)
    opp = Opportunity(
        name=name,
        pipeline_stage_id=stage.id,
        owner_id=owner.id,
        created_by_id=owner.id,
    )
    db.add(opp)
    await db.commit()
    await db.refresh(opp)
    return opp


async def _make_company(db: AsyncSession, owner: User, name: str = "Sample Co") -> Company:
    company = Company(
        name=name,
        owner_id=owner.id,
        created_by_id=owner.id,
    )
    db.add(company)
    await db.commit()
    await db.refresh(company)
    return company


async def _opt_in(db: AsyncSession, user: User, *event_keys: str) -> None:
    """Create an opted-in prefs row for user with in_app + email enabled for each event key."""
    prefs = UserNotificationPrefs(
        user_id=user.id,
        in_app_enabled=True,
        email_enabled=True,
        event_matrix={key: {"in_app": True, "email": True} for key in event_keys},
    )
    db.add(prefs)
    await db.commit()


# ---------------------------------------------------------------------------
# Sharing notifications
# ---------------------------------------------------------------------------


class TestShareNotifications:
    """Notifications fired when a record is shared or assigned."""

    @pytest.mark.asyncio
    async def test_view_share_creates_entity_shared_notification(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """POST /api/sharing with permission_level='view' creates entity_shared_with_you notification for recipient."""
        recipient = await _make_user(db_session, "recipient_view@example.com", "View Recipient")
        contact = await _make_contact(db_session, test_user, "Shared Contact")

        resp = await client.post(
            "/api/sharing",
            headers=_headers(test_user),
            json={
                "entity_type": "contacts",
                "entity_id": contact.id,
                "shared_with_user_id": recipient.id,
                "permission_level": "view",
            },
        )
        assert resp.status_code == 201, resp.text

        result = await db_session.execute(
            select(Notification).where(
                Notification.user_id == recipient.id,
                Notification.type == "entity_shared_with_you",
            )
        )
        notif = result.scalar_one_or_none()
        assert notif is not None
        assert notif.entity_type == "contacts"
        assert notif.entity_id == contact.id

    @pytest.mark.asyncio
    async def test_edit_share_creates_entity_shared_notification(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """POST /api/sharing with permission_level='edit' creates entity_shared_with_you notification."""
        recipient = await _make_user(db_session, "recipient_edit@example.com", "Edit Recipient")
        lead = await _make_lead(db_session, test_user, "Shared Lead")

        resp = await client.post(
            "/api/sharing",
            headers=_headers(test_user),
            json={
                "entity_type": "leads",
                "entity_id": lead.id,
                "shared_with_user_id": recipient.id,
                "permission_level": "edit",
            },
        )
        assert resp.status_code == 201, resp.text

        result = await db_session.execute(
            select(Notification).where(
                Notification.user_id == recipient.id,
                Notification.type == "entity_shared_with_you",
            )
        )
        notif = result.scalar_one_or_none()
        assert notif is not None

    @pytest.mark.asyncio
    async def test_assignee_share_creates_record_assigned_notification(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """POST /api/sharing with permission_level='assignee' creates record_assigned_to_you notification."""
        recipient = await _make_user(db_session, "recipient_assignee@example.com", "Assignee Recipient")
        opp = await _make_opportunity(db_session, test_user, "Shared Opp")

        resp = await client.post(
            "/api/sharing",
            headers=_headers(test_user),
            json={
                "entity_type": "opportunities",
                "entity_id": opp.id,
                "shared_with_user_id": recipient.id,
                "permission_level": "assignee",
            },
        )
        assert resp.status_code == 201, resp.text

        result = await db_session.execute(
            select(Notification).where(
                Notification.user_id == recipient.id,
                Notification.type == "record_assigned_to_you",
            )
        )
        notif = result.scalar_one_or_none()
        assert notif is not None
        assert notif.entity_type == "opportunities"
        assert notif.entity_id == opp.id

    @pytest.mark.asyncio
    async def test_assignee_does_not_create_shared_notification(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """assignee share must not create entity_shared_with_you — only record_assigned_to_you."""
        recipient = await _make_user(db_session, "recipient_assignee2@example.com", "Assignee Only")
        company = await _make_company(db_session, test_user, "Shared Co")

        await client.post(
            "/api/sharing",
            headers=_headers(test_user),
            json={
                "entity_type": "companies",
                "entity_id": company.id,
                "shared_with_user_id": recipient.id,
                "permission_level": "assignee",
            },
        )

        result = await db_session.execute(
            select(Notification).where(
                Notification.user_id == recipient.id,
                Notification.type == "entity_shared_with_you",
            )
        )
        assert result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_only_one_notification_per_share(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Exactly one notification row is created per share event."""
        recipient = await _make_user(db_session, "one_notif@example.com", "One Notif")
        contact = await _make_contact(db_session, test_user, "Once-Notified Contact")

        resp = await client.post(
            "/api/sharing",
            headers=_headers(test_user),
            json={
                "entity_type": "contacts",
                "entity_id": contact.id,
                "shared_with_user_id": recipient.id,
                "permission_level": "view",
            },
        )
        assert resp.status_code == 201, resp.text

        result = await db_session.execute(
            select(Notification).where(Notification.user_id == recipient.id)
        )
        notifs = result.scalars().all()
        assert len(notifs) == 1


# ---------------------------------------------------------------------------
# Proposal signed notifications
# ---------------------------------------------------------------------------


class TestProposalSignedNotification:
    """Owner receives proposal_signed notification when the public sign endpoint fires."""

    @pytest.mark.asyncio
    async def test_public_accept_fires_proposal_signed_notification_to_owner(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_contact,
    ):
        """Signing a proposal via public link notifies the owner with proposal_signed."""
        owner = await _make_user(db_session, "proposal_owner@example.com", "Proposal Owner")
        await _opt_in(db_session, owner, "proposal_signed")

        proposal = Proposal(
            proposal_number="PR-TC-001",
            public_token=secrets.token_urlsafe(32),
            title="Team-Collab Test Proposal",
            status="sent",
            contact_id=test_contact.id,
            owner_id=owner.id,
            created_by_id=owner.id,
        )
        db_session.add(proposal)
        await db_session.commit()
        await db_session.refresh(proposal)

        resp = await client.post(
            f"/api/proposals/public/{proposal.public_token}/accept",
            json={
                "signer_name": "Jane Customer",
                "signer_email": test_contact.email,
                "signature_image": _SIG,
                "agreed_to_terms": True,
            },
        )
        assert resp.status_code == 200, resp.text

        result = await db_session.execute(
            select(Notification).where(
                Notification.user_id == owner.id,
                Notification.type == "proposal_signed",
            )
        )
        notif = result.scalar_one_or_none()
        assert notif is not None
        assert notif.title == "Proposal signed"
        assert "Jane Customer" in notif.message
        assert notif.entity_type == "proposals"
        assert notif.entity_id == proposal.id

    @pytest.mark.asyncio
    async def test_public_accept_notification_not_created_for_signer(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_contact,
    ):
        """The signer (not the owner) must NOT get a proposal_signed notification."""
        owner = await _make_user(db_session, "proposal_owner2@example.com", "Proposal Owner 2")
        await _opt_in(db_session, owner, "proposal_signed")

        proposal = Proposal(
            proposal_number="PR-TC-002",
            public_token=secrets.token_urlsafe(32),
            title="Another Test Proposal",
            status="sent",
            contact_id=test_contact.id,
            owner_id=owner.id,
            created_by_id=owner.id,
        )
        db_session.add(proposal)
        await db_session.commit()
        await db_session.refresh(proposal)

        await client.post(
            f"/api/proposals/public/{proposal.public_token}/accept",
            json={
                "signer_name": "Customer X",
                "signer_email": test_contact.email,
                "signature_image": _SIG,
                "agreed_to_terms": True,
            },
        )

        # Exactly one notification total — to the owner only
        result = await db_session.execute(
            select(Notification).where(Notification.type == "proposal_signed")
        )
        notifs = result.scalars().all()
        assert len(notifs) == 1
        assert notifs[0].user_id == owner.id


# ---------------------------------------------------------------------------
# Contract signed notifications retired 2026-05-14 with the Contracts module
# unmount. /api/contracts/public/{token}/sign no longer exists.
# ---------------------------------------------------------------------------
