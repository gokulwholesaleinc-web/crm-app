"""Tests for public proposal accept/reject endpoints with e-signature audit.

Covers:
- POST /api/proposals/public/{token}/accept
- POST /api/proposals/public/{token}/reject

Validates:
- signer_email must match designated_signer_email (or fall back to contact email)
- signer_name, signer_email, signer_ip, signer_user_agent persisted on accept
- Status guard (only sent/viewed states can be accepted/rejected)
- No mocking — real DB, real ASGI transport
"""

import pytest
import secrets
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.proposals.models import Proposal
from src.contacts.models import Contact


@pytest.fixture
async def sent_proposal(
    db_session: AsyncSession, test_user: User, test_contact: Contact,
) -> Proposal:
    proposal = Proposal(
        proposal_number="PR-2026-SIGN-001",
        public_token=secrets.token_urlsafe(32),
        title="Website Redesign Contract",
        status="sent",
        contact_id=test_contact.id,
        owner_id=test_user.id,
        created_by_id=test_user.id,
    )
    db_session.add(proposal)
    await db_session.commit()
    await db_session.refresh(proposal)
    return proposal


@pytest.fixture
async def draft_proposal(db_session: AsyncSession, test_user: User) -> Proposal:
    proposal = Proposal(
        proposal_number="PR-2026-SIGN-DRAFT",
        public_token=secrets.token_urlsafe(32),
        title="Draft Proposal",
        status="draft",
        owner_id=test_user.id,
        created_by_id=test_user.id,
    )
    db_session.add(proposal)
    await db_session.commit()
    await db_session.refresh(proposal)
    return proposal


class TestPublicProposalAccept:
    """POST /api/proposals/public/{token}/accept"""

    @pytest.mark.asyncio
    async def test_accept_captures_full_signer_audit(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        sent_proposal: Proposal,
        test_contact: Contact,
    ):
        """signer_name + signer_email + signer_ip + signer_user_agent + signed_at all persisted."""
        response = await client.post(
            f"/api/proposals/public/{sent_proposal.public_token}/accept",
            json={"signer_name": "Jane Customer", "signer_email": test_contact.email},
            headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) SignTest/1.0"},
        )
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "accepted"

        await db_session.refresh(sent_proposal)
        assert sent_proposal.status == "accepted"
        assert sent_proposal.signer_name == "Jane Customer"
        assert sent_proposal.signer_email == test_contact.email
        assert sent_proposal.signer_ip is not None
        assert sent_proposal.signer_user_agent == "Mozilla/5.0 (X11; Linux x86_64) SignTest/1.0"
        assert sent_proposal.signed_at is not None
        assert sent_proposal.accepted_at is not None

    @pytest.mark.asyncio
    async def test_accept_rejects_mismatched_signer_email(
        self,
        client: AsyncClient,
        sent_proposal: Proposal,
    ):
        """Signer email that doesn't match the recipient must 400."""
        response = await client.post(
            f"/api/proposals/public/{sent_proposal.public_token}/accept",
            json={"signer_name": "Imposter", "signer_email": "attacker@evil.com"},
        )
        assert response.status_code == 400
        assert "does not match" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_designated_signer_email_overrides_contact(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        sent_proposal: Proposal,
        test_contact: Contact,
    ):
        """designated_signer_email on the proposal wins over contact.email."""
        sent_proposal.designated_signer_email = "cfo@client.example"
        await db_session.commit()

        # Contact email is now the wrong signer
        response = await client.post(
            f"/api/proposals/public/{sent_proposal.public_token}/accept",
            json={"signer_name": "Contact", "signer_email": test_contact.email},
        )
        assert response.status_code == 400

        # Designated email works (case-insensitive)
        response = await client.post(
            f"/api/proposals/public/{sent_proposal.public_token}/accept",
            json={"signer_name": "CFO", "signer_email": "CFO@Client.Example"},
        )
        assert response.status_code == 200, response.text

    @pytest.mark.asyncio
    async def test_accept_rejects_draft_proposal(
        self,
        client: AsyncClient,
        draft_proposal: Proposal,
    ):
        """Only sent/viewed proposals can be accepted; draft must 400."""
        response = await client.post(
            f"/api/proposals/public/{draft_proposal.public_token}/accept",
            json={"signer_name": "x", "signer_email": "x@x.com"},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_accept_unknown_token_returns_404(self, client: AsyncClient):
        response = await client.post(
            "/api/proposals/public/definitely-not-a-real-token-xx/accept",
            json={"signer_name": "x", "signer_email": "x@x.com"},
        )
        assert response.status_code == 404


class TestPublicProposalReject:
    """POST /api/proposals/public/{token}/reject"""

    @pytest.mark.asyncio
    async def test_reject_captures_reason_and_audit(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        sent_proposal: Proposal,
        test_contact: Contact,
    ):
        """rejection_reason + signer_ip + signer_user_agent captured on reject."""
        response = await client.post(
            f"/api/proposals/public/{sent_proposal.public_token}/reject",
            json={
                "signer_email": test_contact.email,
                "reason": "Budget didn't land this quarter",
            },
            headers={"User-Agent": "RejectAgent/1.0"},
        )
        assert response.status_code == 200, response.text

        await db_session.refresh(sent_proposal)
        assert sent_proposal.status == "rejected"
        assert sent_proposal.rejected_at is not None
        assert sent_proposal.rejection_reason == "Budget didn't land this quarter"
        assert sent_proposal.signer_ip is not None
        assert sent_proposal.signer_user_agent == "RejectAgent/1.0"

    @pytest.mark.asyncio
    async def test_reject_requires_signer_email(
        self,
        client: AsyncClient,
        sent_proposal: Proposal,
    ):
        """Reject must now require signer_email to prevent forwarded-link abuse."""
        response = await client.post(
            f"/api/proposals/public/{sent_proposal.public_token}/reject",
            json={},
        )
        assert response.status_code == 422, response.text  # Pydantic validation

    @pytest.mark.asyncio
    async def test_reject_rejects_mismatched_signer_email(
        self,
        client: AsyncClient,
        sent_proposal: Proposal,
    ):
        """A signer_email that doesn't match the contact must be rejected."""
        response = await client.post(
            f"/api/proposals/public/{sent_proposal.public_token}/reject",
            json={"signer_email": "imposter@evil.example.com"},
        )
        assert response.status_code == 400, response.text
        assert "does not match" in response.json()["detail"].lower()
