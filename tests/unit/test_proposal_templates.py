"""
Unit tests for branded proposal templates: email sending, PDF generation,
and public view branding.

Tests for send_proposal_email, generate_proposal_pdf, public view branding,
and proposal email content.
"""

import pytest
from datetime import date, timedelta
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.auth.models import User
from src.auth.security import get_password_hash, create_access_token
from src.proposals.models import Proposal, ProposalView
from src.contacts.models import Contact
from src.companies.models import Company
from src.email.models import EmailQueue
from src.whitelabel.models import Tenant, TenantSettings, TenantUser


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
async def branded_tenant(db_session: AsyncSession) -> Tenant:
    """Create a tenant with branding settings."""
    tenant = Tenant(
        name="Acme Corp",
        slug="acme-corp",
        domain="acme.example.com",
        is_active=True,
        plan="professional",
        max_users=10,
    )
    db_session.add(tenant)
    await db_session.flush()

    settings = TenantSettings(
        tenant_id=tenant.id,
        company_name="Acme Corporation",
        logo_url="https://acme.example.com/logo.png",
        primary_color="#1e40af",
        secondary_color="#3b82f6",
        accent_color="#10b981",
        footer_text="Acme Corp - Excellence in Everything",
    )
    db_session.add(settings)
    await db_session.commit()
    await db_session.refresh(tenant)
    return tenant


@pytest.fixture
async def branded_user(db_session: AsyncSession, branded_tenant: Tenant) -> User:
    """Create a user linked to the branded tenant."""
    user = User(
        email="proposaluser@acme.example.com",
        hashed_password=get_password_hash("testpassword123"),
        full_name="Proposal User",
        is_active=True,
        is_superuser=False,
    )
    db_session.add(user)
    await db_session.flush()

    tenant_user = TenantUser(
        tenant_id=branded_tenant.id,
        user_id=user.id,
        role="admin",
        is_primary=True,
    )
    db_session.add(tenant_user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def branded_auth_headers(branded_user: User) -> dict:
    """Auth headers for the branded user."""
    token = create_access_token(data={"sub": str(branded_user.id)})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def branded_contact(
    db_session: AsyncSession, branded_user: User, test_company: Company
) -> Contact:
    """Create a contact for branded proposal tests."""
    contact = Contact(
        first_name="Alice",
        last_name="Client",
        email="alice.client@example.com",
        phone="+1-555-0200",
        job_title="CTO",
        company_id=test_company.id,
        status="active",
        owner_id=branded_user.id,
        created_by_id=branded_user.id,
    )
    db_session.add(contact)
    await db_session.commit()
    await db_session.refresh(contact)
    return contact


@pytest.fixture
async def branded_proposal(
    db_session: AsyncSession, branded_user: User, branded_contact: Contact
) -> Proposal:
    """Create a proposal owned by the branded user with a contact."""
    proposal = Proposal(
        proposal_number="PR-2026-BRAND01",
        title="Branded Test Proposal",
        content="Full proposal content",
        status="draft",
        executive_summary="Executive summary for branding test",
        scope_of_work="Scope details here",
        pricing_section="$50,000 total",
        timeline="Q1 2026",
        terms="Standard terms apply",
        cover_letter="Dear Alice, we are excited to present this proposal.",
        valid_until=date.today() + timedelta(days=30),
        contact_id=branded_contact.id,
        owner_id=branded_user.id,
        created_by_id=branded_user.id,
    )
    db_session.add(proposal)
    await db_session.commit()
    await db_session.refresh(proposal)
    return proposal


# =============================================================================
# Send Proposal Email Tests
# =============================================================================

class TestSendProposalEmail:
    """Tests for sending branded proposal emails."""

    @pytest.mark.asyncio
    async def test_send_proposal_sends_branded_email(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        branded_auth_headers: dict,
        branded_proposal: Proposal,
        branded_contact: Contact,
    ):
        """Test that sending a proposal creates an email queue entry."""
        response = await client.post(
            f"/api/proposals/{branded_proposal.id}/send",
            headers=branded_auth_headers,
            json={"attach_pdf": False},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "sent"

        # Verify an email was queued
        result = await db_session.execute(
            select(EmailQueue).where(
                EmailQueue.entity_type == "proposals",
                EmailQueue.entity_id == branded_proposal.id,
            )
        )
        emails = result.scalars().all()
        assert len(emails) >= 1

        email = emails[0]
        assert email.to_email == branded_contact.email
        assert "Branded Test Proposal" in email.subject

    @pytest.mark.asyncio
    async def test_send_proposal_email_contains_public_view_link(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        branded_auth_headers: dict,
        branded_proposal: Proposal,
    ):
        """Test that the proposal email contains a link to the public view."""
        response = await client.post(
            f"/api/proposals/{branded_proposal.id}/send",
            headers=branded_auth_headers,
            json={"attach_pdf": False},
        )

        assert response.status_code == 200

        result = await db_session.execute(
            select(EmailQueue).where(
                EmailQueue.entity_type == "proposals",
                EmailQueue.entity_id == branded_proposal.id,
            )
        )
        email = result.scalars().first()
        assert email is not None
        assert branded_proposal.proposal_number in email.body
        assert "proposals/public/" in email.body

    @pytest.mark.asyncio
    async def test_send_proposal_marks_status_sent(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        branded_auth_headers: dict,
        branded_proposal: Proposal,
    ):
        """Test that sending marks the proposal as sent."""
        response = await client.post(
            f"/api/proposals/{branded_proposal.id}/send",
            headers=branded_auth_headers,
            json={"attach_pdf": False},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "sent"
        assert data["sent_at"] is not None

    @pytest.mark.asyncio
    async def test_send_proposal_without_contact_fails(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        branded_auth_headers: dict,
        branded_user: User,
    ):
        """Test that sending a proposal without a contact returns 400."""
        proposal = Proposal(
            proposal_number="PR-2026-NOCON",
            title="No Contact Proposal",
            status="draft",
            owner_id=branded_user.id,
            created_by_id=branded_user.id,
        )
        db_session.add(proposal)
        await db_session.commit()
        await db_session.refresh(proposal)

        response = await client.post(
            f"/api/proposals/{proposal.id}/send",
            headers=branded_auth_headers,
            json={"attach_pdf": False},
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_send_proposal_email_is_branded(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        branded_auth_headers: dict,
        branded_proposal: Proposal,
    ):
        """Test that the email body includes tenant branding elements."""
        response = await client.post(
            f"/api/proposals/{branded_proposal.id}/send",
            headers=branded_auth_headers,
            json={"attach_pdf": False},
        )
        assert response.status_code == 200

        result = await db_session.execute(
            select(EmailQueue).where(
                EmailQueue.entity_type == "proposals",
                EmailQueue.entity_id == branded_proposal.id,
            )
        )
        email = result.scalars().first()
        assert email is not None
        # The branded template should include company name
        assert "Acme Corporation" in email.body or "Acme Corp" in email.subject


# =============================================================================
# Generate Proposal PDF Tests
# =============================================================================

class TestGenerateProposalPDF:
    """Tests for branded proposal PDF generation."""

    @pytest.mark.asyncio
    async def test_generate_proposal_pdf_returns_content(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        branded_auth_headers: dict,
        branded_proposal: Proposal,
    ):
        """Test that the PDF endpoint returns content."""
        response = await client.get(
            f"/api/proposals/{branded_proposal.id}/pdf",
            headers=branded_auth_headers,
        )

        assert response.status_code == 200
        assert len(response.content) > 0
        # Content-Disposition header should suggest a filename
        content_disp = response.headers.get("content-disposition", "")
        assert "proposal-" in content_disp
        assert branded_proposal.proposal_number in content_disp

    @pytest.mark.asyncio
    async def test_generate_pdf_not_found(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        branded_auth_headers: dict,
    ):
        """Test PDF generation for non-existent proposal returns 404."""
        response = await client.get(
            "/api/proposals/99999/pdf",
            headers=branded_auth_headers,
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_generate_pdf_unauthorized(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        branded_proposal: Proposal,
    ):
        """Test PDF generation without auth returns 401."""
        response = await client.get(
            f"/api/proposals/{branded_proposal.id}/pdf",
        )

        assert response.status_code == 401


# =============================================================================
# Public View Branding Tests
# =============================================================================

class TestPublicViewBranding:
    """Tests for branding data in public proposal view."""

    @pytest.mark.asyncio
    async def test_public_view_includes_branding(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        branded_proposal: Proposal,
    ):
        """Test that the public view response includes branding data."""
        response = await client.get(
            f"/api/proposals/public/{branded_proposal.proposal_number}",
        )

        assert response.status_code == 200
        data = response.json()
        assert "branding" in data
        branding = data["branding"]
        assert branding is not None
        assert branding["company_name"] == "Acme Corporation"
        assert branding["logo_url"] == "https://acme.example.com/logo.png"
        assert branding["primary_color"] == "#1e40af"
        assert branding["secondary_color"] == "#3b82f6"
        assert branding["accent_color"] == "#10b981"

    @pytest.mark.asyncio
    async def test_public_view_default_branding_without_tenant(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test that proposals without tenant owner get default branding."""
        proposal = Proposal(
            proposal_number="PR-2026-NOBRAND",
            title="No Brand Proposal",
            status="draft",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(proposal)
        await db_session.commit()
        await db_session.refresh(proposal)

        response = await client.get(
            f"/api/proposals/public/{proposal.proposal_number}",
        )

        assert response.status_code == 200
        data = response.json()
        assert "branding" in data
        branding = data["branding"]
        assert branding is not None
        # Should have default colors
        assert branding["primary_color"] == "#6366f1"
        assert branding["secondary_color"] == "#8b5cf6"

    @pytest.mark.asyncio
    async def test_public_view_includes_proposal_content(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        branded_proposal: Proposal,
    ):
        """Test that public view still includes all proposal sections."""
        response = await client.get(
            f"/api/proposals/public/{branded_proposal.proposal_number}",
        )

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Branded Test Proposal"
        assert data["executive_summary"] == "Executive summary for branding test"
        assert data["scope_of_work"] == "Scope details here"
        assert data["pricing_section"] == "$50,000 total"
        assert data["timeline"] == "Q1 2026"
        assert data["terms"] == "Standard terms apply"
        assert data["cover_letter"] is not None

    @pytest.mark.asyncio
    async def test_public_view_branding_has_footer_text(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        branded_proposal: Proposal,
    ):
        """Test that branding includes footer text from tenant settings."""
        response = await client.get(
            f"/api/proposals/public/{branded_proposal.proposal_number}",
        )

        assert response.status_code == 200
        data = response.json()
        branding = data["branding"]
        assert branding["footer_text"] == "Acme Corp - Excellence in Everything"
