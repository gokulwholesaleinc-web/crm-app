"""Integration tests for the post-sign email + owner notification flow.

Tests verify:
 1. accept_proposal_public queues a signer-side EmailQueue row with the branded
    "Signed copy" subject and an owner-side row with "Proposal signed".
 2. When proposal_signed email is disabled in the matrix the signer-side row
    still exists (always-on) but the owner-side row does not.
 3. An in-app Notification row of type proposal_signed is created for the owner.

All assertions hit the real SQLite in-memory DB (no DB mocks). PDF generation
is patched to return dummy bytes so weasyprint's system-lib requirement does
not block the test environment.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.account.models import UserNotificationPrefs
from src.auth.models import User
from src.companies.models import Company
from src.contacts.models import Contact
from src.email.models import EmailQueue
from src.notifications.models import Notification
from src.proposals.models import Proposal
from src.proposals.service import ProposalService
from src.whitelabel.models import Tenant, TenantUser


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DUMMY_PDF = b"%PDF-1.4 dummy"


async def _make_proposal(
    db: AsyncSession,
    owner: User,
    contact: Contact,
    *,
    signer_email: str = "signer@example.com",
) -> Proposal:
    proposal = Proposal(
        proposal_number=f"P-{secrets.token_hex(4).upper()}",
        title="Test Proposal",
        status="sent",
        owner_id=owner.id,
        contact_id=contact.id,
        public_token=secrets.token_urlsafe(32),
        # Set designated_signer_email so accept_proposal_public skips contact lookup
        designated_signer_email=signer_email,
    )
    db.add(proposal)
    await db.commit()
    await db.refresh(proposal)
    return proposal


async def _accept(
    db: AsyncSession,
    proposal: Proposal,
    signer_email: str = "signer@example.com",
) -> Proposal:
    """Call accept_proposal_public with PDF generation stubbed out."""
    svc = ProposalService(db)
    with patch.object(svc, "generate_proposal_pdf", new=AsyncMock(return_value=_DUMMY_PDF)):
        return await svc.accept_proposal_public(
            proposal,
            signer_name="Jane Signer",
            signer_email=signer_email,
        )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestProposalSignedEmails:
    """Post-sign email + notification wiring."""

    async def test_signer_and_owner_email_queued(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_contact: Contact,
        test_tenant: Tenant,
        test_tenant_user: TenantUser,
    ):
        """accept_proposal_public creates signer-side AND owner-side EmailQueue rows."""
        proposal = await _make_proposal(db_session, test_user, test_contact)

        await _accept(db_session, proposal)

        rows = (
            await db_session.execute(
                select(EmailQueue)
                .where(EmailQueue.entity_type == "proposals")
                .where(EmailQueue.entity_id == proposal.id)
            )
        ).scalars().all()

        subjects = {r.subject for r in rows}

        assert any("Signed copy" in s and "Test Proposal" in s for s in subjects), (
            f"Expected signer-side 'Signed copy' email; got subjects: {subjects}"
        )
        assert any("Proposal signed" in s and "Test Proposal" in s for s in subjects), (
            f"Expected owner-side 'Proposal signed' email; got subjects: {subjects}"
        )

    async def test_owner_email_suppressed_by_matrix(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_contact: Contact,
        test_tenant: Tenant,
        test_tenant_user: TenantUser,
    ):
        """When proposal_signed email is off in the matrix, owner email is not queued."""
        prefs = UserNotificationPrefs(
            user_id=test_user.id,
            in_app_enabled=True,
            email_enabled=True,
            email_digest="instant",
            event_matrix={"proposal_signed": {"email": False}},
        )
        db_session.add(prefs)
        await db_session.commit()

        proposal = await _make_proposal(db_session, test_user, test_contact)

        await _accept(db_session, proposal)

        rows = (
            await db_session.execute(
                select(EmailQueue)
                .where(EmailQueue.entity_type == "proposals")
                .where(EmailQueue.entity_id == proposal.id)
            )
        ).scalars().all()

        subjects = {r.subject for r in rows}

        assert any("Signed copy" in s for s in subjects), (
            "Signer-side email must always be queued regardless of matrix"
        )
        assert not any("Proposal signed" in s for s in subjects), (
            f"Owner email should be suppressed by matrix; got subjects: {subjects}"
        )

    async def test_owner_in_app_notification_created(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_contact: Contact,
        test_tenant: Tenant,
        test_tenant_user: TenantUser,
    ):
        """An in-app Notification of type proposal_signed is created for the owner."""
        proposal = await _make_proposal(db_session, test_user, test_contact)

        await _accept(db_session, proposal)

        notif = (
            await db_session.execute(
                select(Notification)
                .where(Notification.user_id == test_user.id)
                .where(Notification.type == "proposal_signed")
                .where(Notification.entity_type == "proposals")
                .where(Notification.entity_id == proposal.id)
            )
        ).scalar_one_or_none()

        assert notif is not None, "Expected an in-app Notification of type proposal_signed"
        assert "Test Proposal" in notif.message
