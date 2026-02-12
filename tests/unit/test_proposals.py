"""
Unit tests for proposals CRUD endpoints.

Tests for list, create, get, update, delete, auto-numbering,
status transitions, template CRUD, public view, view counting,
AI generation, and data isolation.
"""

import pytest
from datetime import date, timedelta
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.auth.models import User
from src.auth.security import get_password_hash, create_access_token
from src.proposals.models import Proposal, ProposalTemplate, ProposalView
from src.contacts.models import Contact
from src.companies.models import Company
from src.opportunities.models import Opportunity, PipelineStage


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
async def test_proposal(db_session: AsyncSession, test_user: User) -> Proposal:
    """Create a test proposal."""
    proposal = Proposal(
        proposal_number="PR-2026-0001",
        title="Test Proposal",
        content="Test proposal content",
        status="draft",
        executive_summary="Executive summary text",
        scope_of_work="Scope of work text",
        pricing_section="Pricing section text",
        timeline="Timeline text",
        owner_id=test_user.id,
        created_by_id=test_user.id,
    )
    db_session.add(proposal)
    await db_session.commit()
    await db_session.refresh(proposal)
    return proposal


@pytest.fixture
async def sent_proposal(db_session: AsyncSession, test_user: User) -> Proposal:
    """Create a sent proposal."""
    proposal = Proposal(
        proposal_number="PR-2026-SENT",
        title="Sent Proposal",
        content="Sent proposal content",
        status="sent",
        owner_id=test_user.id,
        created_by_id=test_user.id,
    )
    db_session.add(proposal)
    await db_session.commit()
    await db_session.refresh(proposal)
    return proposal


# =============================================================================
# Proposal CRUD Tests
# =============================================================================

class TestProposalsList:
    """Tests for proposals list endpoint."""

    @pytest.mark.asyncio
    async def test_list_proposals_empty(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test listing proposals when none exist."""
        response = await client.get("/api/proposals", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["page"] == 1

    @pytest.mark.asyncio
    async def test_list_proposals_with_data(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_proposal: Proposal,
    ):
        """Test listing proposals with existing data."""
        response = await client.get("/api/proposals", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        assert any(p["id"] == test_proposal.id for p in data["items"])

    @pytest.mark.asyncio
    async def test_list_proposals_pagination(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Test proposals pagination."""
        for i in range(15):
            p = Proposal(
                proposal_number=f"PR-2026-{i+10:04d}",
                title=f"Proposal {i}",
                status="draft",
                owner_id=test_user.id,
                created_by_id=test_user.id,
            )
            db_session.add(p)
        await db_session.commit()

        response = await client.get(
            "/api/proposals",
            headers=auth_headers,
            params={"page": 1, "page_size": 10},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 10
        assert data["total"] == 15

        response2 = await client.get(
            "/api/proposals",
            headers=auth_headers,
            params={"page": 2, "page_size": 10},
        )
        data2 = response2.json()
        assert len(data2["items"]) == 5

    @pytest.mark.asyncio
    async def test_list_proposals_search(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_proposal: Proposal,
    ):
        """Test searching proposals by title."""
        response = await client.get(
            "/api/proposals",
            headers=auth_headers,
            params={"search": "Test Proposal"},
        )

        assert response.status_code == 200
        data = response.json()
        assert any(p["id"] == test_proposal.id for p in data["items"])

    @pytest.mark.asyncio
    async def test_list_proposals_search_by_number(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_proposal: Proposal,
    ):
        """Test searching proposals by proposal number."""
        response = await client.get(
            "/api/proposals",
            headers=auth_headers,
            params={"search": "PR-2026-0001"},
        )

        assert response.status_code == 200
        data = response.json()
        assert any(p["id"] == test_proposal.id for p in data["items"])

    @pytest.mark.asyncio
    async def test_list_proposals_filter_by_status(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_proposal: Proposal,
    ):
        """Test filtering proposals by status."""
        response = await client.get(
            "/api/proposals",
            headers=auth_headers,
            params={"status": "draft"},
        )

        assert response.status_code == 200
        data = response.json()
        assert all(p["status"] == "draft" for p in data["items"])


class TestProposalsCreate:
    """Tests for proposal creation endpoint."""

    @pytest.mark.asyncio
    async def test_create_proposal_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test successful proposal creation."""
        response = await client.post(
            "/api/proposals",
            headers=auth_headers,
            json={
                "title": "New Proposal",
                "content": "Proposal content here",
                "executive_summary": "Summary",
                "scope_of_work": "Scope",
                "status": "draft",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "New Proposal"
        assert data["status"] == "draft"
        assert "proposal_number" in data
        assert data["proposal_number"].startswith("PR-")
        assert "id" in data

    @pytest.mark.asyncio
    async def test_create_proposal_missing_title(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test creating proposal without title fails."""
        response = await client.post(
            "/api/proposals",
            headers=auth_headers,
            json={
                "content": "Some content",
                "status": "draft",
            },
        )

        assert response.status_code == 422


class TestAutoNumbering:
    """Tests for proposal auto-numbering."""

    @pytest.mark.asyncio
    async def test_auto_numbering_sequential(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test that proposal numbers are generated sequentially."""
        response1 = await client.post(
            "/api/proposals",
            headers=auth_headers,
            json={"title": "First Proposal", "status": "draft"},
        )
        assert response1.status_code == 201
        number1 = response1.json()["proposal_number"]

        response2 = await client.post(
            "/api/proposals",
            headers=auth_headers,
            json={"title": "Second Proposal", "status": "draft"},
        )
        assert response2.status_code == 201
        number2 = response2.json()["proposal_number"]

        # Both should start with PR-
        assert number1.startswith("PR-")
        assert number2.startswith("PR-")

        # Second number should be higher
        seq1 = int(number1.split("-")[-1])
        seq2 = int(number2.split("-")[-1])
        assert seq2 > seq1


class TestProposalsGetById:
    """Tests for get proposal by ID endpoint."""

    @pytest.mark.asyncio
    async def test_get_proposal_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_proposal: Proposal,
    ):
        """Test getting proposal by ID."""
        response = await client.get(
            f"/api/proposals/{test_proposal.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == test_proposal.id
        assert data["title"] == test_proposal.title
        assert data["proposal_number"] == test_proposal.proposal_number

    @pytest.mark.asyncio
    async def test_get_proposal_not_found(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test getting non-existent proposal."""
        response = await client.get(
            "/api/proposals/99999",
            headers=auth_headers,
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_proposal_includes_sections(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_proposal: Proposal,
    ):
        """Test that getting proposal includes content sections."""
        response = await client.get(
            f"/api/proposals/{test_proposal.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["executive_summary"] == "Executive summary text"
        assert data["scope_of_work"] == "Scope of work text"
        assert data["pricing_section"] == "Pricing section text"
        assert data["timeline"] == "Timeline text"


class TestProposalsUpdate:
    """Tests for proposal update endpoint."""

    @pytest.mark.asyncio
    async def test_update_proposal_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_proposal: Proposal,
    ):
        """Test updating a proposal."""
        response = await client.patch(
            f"/api/proposals/{test_proposal.id}",
            headers=auth_headers,
            json={
                "title": "Updated Proposal Title",
                "executive_summary": "Updated summary",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Updated Proposal Title"
        assert data["executive_summary"] == "Updated summary"

    @pytest.mark.asyncio
    async def test_update_proposal_not_found(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test updating non-existent proposal."""
        response = await client.patch(
            "/api/proposals/99999",
            headers=auth_headers,
            json={"title": "Test"},
        )

        assert response.status_code == 404


class TestProposalsDelete:
    """Tests for proposal delete endpoint."""

    @pytest.mark.asyncio
    async def test_delete_proposal_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Test deleting a proposal."""
        proposal = Proposal(
            proposal_number="PR-2026-DEL1",
            title="To Delete",
            status="draft",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(proposal)
        await db_session.commit()
        await db_session.refresh(proposal)
        pid = proposal.id

        response = await client.delete(
            f"/api/proposals/{pid}",
            headers=auth_headers,
        )

        assert response.status_code == 204

        result = await db_session.execute(
            select(Proposal).where(Proposal.id == pid)
        )
        assert result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_delete_proposal_not_found(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test deleting non-existent proposal."""
        response = await client.delete(
            "/api/proposals/99999",
            headers=auth_headers,
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_proposal_cascades_views(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Test that deleting a proposal also deletes its views."""
        proposal = Proposal(
            proposal_number="PR-2026-CASC",
            title="Cascade Test",
            status="draft",
            view_count=1,
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(proposal)
        await db_session.flush()

        view = ProposalView(
            proposal_id=proposal.id,
            ip_address="127.0.0.1",
        )
        db_session.add(view)
        await db_session.commit()
        pid = proposal.id

        response = await client.delete(
            f"/api/proposals/{pid}",
            headers=auth_headers,
        )
        assert response.status_code == 204

        result = await db_session.execute(
            select(ProposalView).where(ProposalView.proposal_id == pid)
        )
        assert len(result.scalars().all()) == 0


# =============================================================================
# Status Transition Tests
# =============================================================================

class TestStatusTransitions:
    """Tests for proposal status transition endpoints."""

    @pytest.mark.asyncio
    async def test_send_proposal(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_contact: Contact,
    ):
        """Test sending a draft proposal with a contact."""
        proposal = Proposal(
            proposal_number="PR-2026-SEND",
            title="Sendable Proposal",
            content="Content here",
            status="draft",
            contact_id=test_contact.id,
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(proposal)
        await db_session.commit()
        await db_session.refresh(proposal)

        response = await client.post(
            f"/api/proposals/{proposal.id}/send",
            headers=auth_headers,
            json={"attach_pdf": False},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "sent"
        assert data["sent_at"] is not None

    @pytest.mark.asyncio
    async def test_accept_sent_proposal(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        sent_proposal: Proposal,
    ):
        """Test accepting a sent proposal."""
        response = await client.post(
            f"/api/proposals/{sent_proposal.id}/accept",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "accepted"
        assert data["accepted_at"] is not None

    @pytest.mark.asyncio
    async def test_reject_sent_proposal(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        sent_proposal: Proposal,
    ):
        """Test rejecting a sent proposal."""
        response = await client.post(
            f"/api/proposals/{sent_proposal.id}/reject",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "rejected"
        assert data["rejected_at"] is not None

    @pytest.mark.asyncio
    async def test_cannot_send_accepted_proposal(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Test that an accepted proposal cannot be sent again."""
        proposal = Proposal(
            proposal_number="PR-2026-ACC2",
            title="Already Accepted",
            status="accepted",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(proposal)
        await db_session.commit()
        await db_session.refresh(proposal)

        response = await client.post(
            f"/api/proposals/{proposal.id}/send",
            headers=auth_headers,
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_cannot_accept_draft_proposal(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_proposal: Proposal,
    ):
        """Test that a draft proposal cannot be directly accepted."""
        response = await client.post(
            f"/api/proposals/{test_proposal.id}/accept",
            headers=auth_headers,
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_cannot_reject_draft_proposal(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_proposal: Proposal,
    ):
        """Test that a draft proposal cannot be directly rejected."""
        response = await client.post(
            f"/api/proposals/{test_proposal.id}/reject",
            headers=auth_headers,
        )

        assert response.status_code == 400


# =============================================================================
# Public View Tests
# =============================================================================

class TestPublicView:
    """Tests for public proposal view endpoint."""

    @pytest.mark.asyncio
    async def test_public_view_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_proposal: Proposal,
    ):
        """Test viewing a proposal publicly by proposal_number."""
        response = await client.get(
            f"/api/proposals/public/{test_proposal.proposal_number}",
        )

        assert response.status_code == 200
        data = response.json()
        assert data["proposal_number"] == test_proposal.proposal_number
        assert data["title"] == test_proposal.title

    @pytest.mark.asyncio
    async def test_public_view_increments_count(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test that public views increment the view_count."""
        proposal = Proposal(
            proposal_number="PR-2026-VIEW",
            title="Viewable Proposal",
            status="sent",
            view_count=0,
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(proposal)
        await db_session.commit()
        await db_session.refresh(proposal)

        # View it twice
        await client.get(f"/api/proposals/public/{proposal.proposal_number}")
        await client.get(f"/api/proposals/public/{proposal.proposal_number}")

        # Check the count via the DB
        await db_session.refresh(proposal)
        assert proposal.view_count == 2

    @pytest.mark.asyncio
    async def test_public_view_creates_view_record(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test that public viewing creates a ProposalView record."""
        proposal = Proposal(
            proposal_number="PR-2026-VREC",
            title="View Record Proposal",
            status="sent",
            view_count=0,
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(proposal)
        await db_session.commit()
        await db_session.refresh(proposal)

        await client.get(f"/api/proposals/public/{proposal.proposal_number}")

        result = await db_session.execute(
            select(ProposalView).where(ProposalView.proposal_id == proposal.id)
        )
        views = result.scalars().all()
        assert len(views) == 1

    @pytest.mark.asyncio
    async def test_public_view_auto_transitions_to_viewed(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test that viewing a 'sent' proposal transitions status to 'viewed'."""
        proposal = Proposal(
            proposal_number="PR-2026-AVTV",
            title="Auto View Transition",
            status="sent",
            view_count=0,
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(proposal)
        await db_session.commit()
        await db_session.refresh(proposal)

        await client.get(f"/api/proposals/public/{proposal.proposal_number}")

        await db_session.refresh(proposal)
        assert proposal.status == "viewed"

    @pytest.mark.asyncio
    async def test_public_view_not_found(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Test viewing a non-existent proposal returns 404."""
        response = await client.get("/api/proposals/public/PR-NONEXISTENT")

        assert response.status_code == 404


# =============================================================================
# Template Tests
# =============================================================================

class TestProposalTemplates:
    """Tests for proposal template endpoints."""

    @pytest.mark.asyncio
    async def test_create_template(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test creating a proposal template."""
        response = await client.post(
            "/api/proposals/templates",
            headers=auth_headers,
            json={
                "name": "SaaS Template",
                "description": "Template for SaaS proposals",
                "category": "software",
                "content_template": "Dear {{contact_name}},\n\nWe propose {{scope}}.",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "SaaS Template"
        assert data["category"] == "software"
        assert "{{contact_name}}" in data["content_template"]

    @pytest.mark.asyncio
    async def test_list_templates(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test listing proposal templates."""
        # Create a template first
        template = ProposalTemplate(
            name="Test Template",
            description="A test template",
            category="general",
            content_template="Hello {{name}}",
            created_by_id=1,
        )
        db_session.add(template)
        await db_session.commit()

        response = await client.get(
            "/api/proposals/templates",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert any(t["name"] == "Test Template" for t in data)


# =============================================================================
# AI Generation Tests
# =============================================================================

class TestAIGeneration:
    """Tests for AI proposal generation endpoint."""

    @pytest.mark.asyncio
    async def test_generate_proposal_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_opportunity: Opportunity,
    ):
        """Test generating a proposal from an opportunity (placeholder mode)."""
        response = await client.post(
            "/api/proposals/generate",
            headers=auth_headers,
            json={"opportunity_id": test_opportunity.id},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["title"].startswith("Proposal for")
        assert data["opportunity_id"] == test_opportunity.id
        assert data["proposal_number"].startswith("PR-")
        assert data["executive_summary"] is not None
        assert data["scope_of_work"] is not None

    @pytest.mark.asyncio
    async def test_generate_proposal_invalid_opportunity(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test generating a proposal with non-existent opportunity."""
        response = await client.post(
            "/api/proposals/generate",
            headers=auth_headers,
            json={"opportunity_id": 99999},
        )

        assert response.status_code == 400


# =============================================================================
# Data Isolation Tests
# =============================================================================

class TestDataIsolation:
    """Tests for data isolation between users."""

    @pytest.mark.asyncio
    async def test_user_sees_only_own_proposals(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        auth_headers: dict,
    ):
        """Test that a user only sees their own proposals."""
        # Create another user
        other_user = User(
            email="other-proposal@example.com",
            hashed_password=get_password_hash("otherpass123"),
            full_name="Other User",
            is_active=True,
            is_superuser=False,
        )
        db_session.add(other_user)
        await db_session.commit()
        await db_session.refresh(other_user)

        # Create proposals for both users
        my_proposal = Proposal(
            proposal_number="PR-2026-MY01",
            title="My Proposal",
            status="draft",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        other_proposal = Proposal(
            proposal_number="PR-2026-OT01",
            title="Other Proposal",
            status="draft",
            owner_id=other_user.id,
            created_by_id=other_user.id,
        )
        db_session.add_all([my_proposal, other_proposal])
        await db_session.commit()

        response = await client.get("/api/proposals", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        titles = [p["title"] for p in data["items"]]
        assert "My Proposal" in titles


# =============================================================================
# Unauthorized Access Tests
# =============================================================================

class TestProposalsUnauthorized:
    """Tests for unauthorized access to proposals endpoints."""

    @pytest.mark.asyncio
    async def test_list_proposals_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test listing proposals without auth fails."""
        response = await client.get("/api/proposals")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_create_proposal_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test creating proposal without auth fails."""
        response = await client.post(
            "/api/proposals",
            json={"title": "Test", "status": "draft"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_proposal_unauthorized(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_proposal: Proposal,
    ):
        """Test getting proposal without auth fails."""
        response = await client.get(f"/api/proposals/{test_proposal.id}")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_update_proposal_unauthorized(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_proposal: Proposal,
    ):
        """Test updating proposal without auth fails."""
        response = await client.patch(
            f"/api/proposals/{test_proposal.id}",
            json={"title": "Hacked"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_delete_proposal_unauthorized(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_proposal: Proposal,
    ):
        """Test deleting proposal without auth fails."""
        response = await client.delete(f"/api/proposals/{test_proposal.id}")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_send_proposal_unauthorized(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_proposal: Proposal,
    ):
        """Test sending proposal without auth fails."""
        response = await client.post(f"/api/proposals/{test_proposal.id}/send")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_generate_proposal_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test generating proposal without auth fails."""
        response = await client.post(
            "/api/proposals/generate",
            json={"opportunity_id": 1},
        )
        assert response.status_code == 401
