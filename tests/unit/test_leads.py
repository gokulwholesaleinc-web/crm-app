"""
Unit tests for leads CRUD and scoring endpoints.

Tests for list, create, get, update, delete, and lead scoring operations.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.auth.models import User
from src.leads.models import Lead, LeadSource
from src.leads.scoring import LeadScorer, calculate_lead_score


class TestLeadsList:
    """Tests for leads list endpoint with pagination."""

    @pytest.mark.asyncio
    async def test_list_leads_empty(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test listing leads when none exist."""
        response = await client.get("/api/leads", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["page"] == 1

    @pytest.mark.asyncio
    async def test_list_leads_with_data(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_lead: Lead,
    ):
        """Test listing leads with existing data."""
        response = await client.get("/api/leads", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        assert len(data["items"]) >= 1
        assert any(lead["id"] == test_lead.id for lead in data["items"])

    @pytest.mark.asyncio
    async def test_list_leads_pagination(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Test leads pagination."""
        # Create multiple leads
        for i in range(15):
            lead = Lead(
                first_name=f"Lead{i}",
                last_name="Test",
                email=f"lead{i}@example.com",
                status="new",
                owner_id=test_user.id,
                created_by_id=test_user.id,
            )
            db_session.add(lead)
        await db_session.commit()

        # First page
        response = await client.get(
            "/api/leads",
            headers=auth_headers,
            params={"page": 1, "page_size": 10},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 10
        assert data["page"] == 1
        assert data["total"] == 15

        # Second page
        response = await client.get(
            "/api/leads",
            headers=auth_headers,
            params={"page": 2, "page_size": 10},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 5

    @pytest.mark.asyncio
    async def test_list_leads_filter_by_status(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_lead: Lead,
    ):
        """Test filtering leads by status."""
        response = await client.get(
            "/api/leads",
            headers=auth_headers,
            params={"status": "new"},
        )

        assert response.status_code == 200
        data = response.json()
        assert all(lead["status"] == "new" for lead in data["items"])

    @pytest.mark.asyncio
    async def test_list_leads_filter_by_source(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_lead: Lead,
        test_lead_source: LeadSource,
    ):
        """Test filtering leads by source."""
        response = await client.get(
            "/api/leads",
            headers=auth_headers,
            params={"source_id": test_lead_source.id},
        )

        assert response.status_code == 200
        data = response.json()
        assert all(
            lead["source"]["id"] == test_lead_source.id
            for lead in data["items"]
            if lead.get("source")
        )

    @pytest.mark.asyncio
    async def test_list_leads_filter_by_min_score(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_lead: Lead,
    ):
        """Test filtering leads by minimum score."""
        response = await client.get(
            "/api/leads",
            headers=auth_headers,
            params={"min_score": 40},
        )

        assert response.status_code == 200
        data = response.json()
        assert all(lead["score"] >= 40 for lead in data["items"])

    @pytest.mark.asyncio
    async def test_list_leads_search(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_lead: Lead,
    ):
        """Test searching leads."""
        response = await client.get(
            "/api/leads",
            headers=auth_headers,
            params={"search": test_lead.first_name},
        )

        assert response.status_code == 200
        data = response.json()
        assert any(lead["id"] == test_lead.id for lead in data["items"])


class TestLeadsCreate:
    """Tests for lead creation endpoint."""

    @pytest.mark.asyncio
    async def test_create_lead_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_lead_source: LeadSource,
    ):
        """Test successful lead creation."""
        response = await client.post(
            "/api/leads",
            headers=auth_headers,
            json={
                "first_name": "New",
                "last_name": "Lead",
                "email": "new.lead@example.com",
                "phone": "+1-555-0200",
                "company_name": "Startup Inc",
                "industry": "Technology",
                "source_id": test_lead_source.id,
                "status": "new",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["first_name"] == "New"
        assert data["last_name"] == "Lead"
        assert data["email"] == "new.lead@example.com"
        assert data["status"] == "new"
        assert "id" in data
        assert data["full_name"] == "New Lead"
        # Lead scoring should be applied
        assert "score" in data

    @pytest.mark.asyncio
    async def test_create_lead_minimal(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test creating lead with minimal required fields."""
        response = await client.post(
            "/api/leads",
            headers=auth_headers,
            json={
                "first_name": "Minimal",
                "last_name": "Lead",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["first_name"] == "Minimal"
        assert data["status"] == "new"  # Default

    @pytest.mark.asyncio
    async def test_create_lead_missing_first_name(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test creating lead without first_name fails."""
        response = await client.post(
            "/api/leads",
            headers=auth_headers,
            json={
                "last_name": "Lead",
                "email": "nofirst@example.com",
            },
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_lead_with_budget(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test creating lead with budget information."""
        response = await client.post(
            "/api/leads",
            headers=auth_headers,
            json={
                "first_name": "Budget",
                "last_name": "Lead",
                "email": "budget.lead@example.com",
                "budget_amount": 75000.0,
                "budget_currency": "USD",
                "company_name": "Big Corp",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["budget_amount"] == 75000.0
        assert data["budget_currency"] == "USD"
        # High budget should increase score
        assert data["score"] > 0

    @pytest.mark.asyncio
    async def test_create_lead_with_all_fields(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_lead_source: LeadSource,
        test_user: User,
    ):
        """Test creating lead with all fields populated."""
        response = await client.post(
            "/api/leads",
            headers=auth_headers,
            json={
                "first_name": "Complete",
                "last_name": "Lead",
                "email": "complete.lead@example.com",
                "phone": "+1-555-0210",
                "mobile": "+1-555-0211",
                "job_title": "CEO",
                "company_name": "Complete Corp",
                "website": "https://complete.com",
                "industry": "Technology",
                "source_id": test_lead_source.id,
                "source_details": "Found via Google search",
                "address_line1": "456 Oak Ave",
                "city": "Boston",
                "state": "MA",
                "postal_code": "02101",
                "country": "USA",
                "description": "A very complete lead",
                "requirements": "Needs enterprise solution",
                "budget_amount": 100000.0,
                "budget_currency": "USD",
                "owner_id": test_user.id,
                "status": "new",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["website"] == "https://complete.com"
        assert data["industry"] == "Technology"
        assert data["requirements"] == "Needs enterprise solution"


class TestLeadsGetById:
    """Tests for get lead by ID endpoint."""

    @pytest.mark.asyncio
    async def test_get_lead_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_lead: Lead,
    ):
        """Test getting lead by ID."""
        response = await client.get(
            f"/api/leads/{test_lead.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == test_lead.id
        assert data["first_name"] == test_lead.first_name
        assert data["last_name"] == test_lead.last_name
        assert data["score"] == test_lead.score

    @pytest.mark.asyncio
    async def test_get_lead_not_found(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test getting non-existent lead."""
        response = await client.get(
            "/api/leads/99999",
            headers=auth_headers,
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_get_lead_includes_source(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_lead: Lead,
        test_lead_source: LeadSource,
    ):
        """Test that getting lead includes source info."""
        response = await client.get(
            f"/api/leads/{test_lead.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["source"] is not None
        assert data["source"]["id"] == test_lead_source.id
        assert data["source"]["name"] == test_lead_source.name


class TestLeadsUpdate:
    """Tests for lead update endpoint."""

    @pytest.mark.asyncio
    async def test_update_lead_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_lead: Lead,
    ):
        """Test updating lead."""
        response = await client.patch(
            f"/api/leads/{test_lead.id}",
            headers=auth_headers,
            json={
                "first_name": "UpdatedLead",
                "company_name": "Updated Company",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["first_name"] == "UpdatedLead"
        assert data["company_name"] == "Updated Company"
        # Other fields unchanged
        assert data["last_name"] == test_lead.last_name

    @pytest.mark.asyncio
    async def test_update_lead_not_found(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test updating non-existent lead."""
        response = await client.patch(
            "/api/leads/99999",
            headers=auth_headers,
            json={"first_name": "Test"},
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_lead_status(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_lead: Lead,
    ):
        """Test updating lead status."""
        response = await client.patch(
            f"/api/leads/{test_lead.id}",
            headers=auth_headers,
            json={"status": "contacted"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "contacted"

    @pytest.mark.asyncio
    async def test_update_lead_to_qualified(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_lead: Lead,
    ):
        """Test updating lead to qualified status."""
        response = await client.patch(
            f"/api/leads/{test_lead.id}",
            headers=auth_headers,
            json={"status": "qualified"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "qualified"

    @pytest.mark.asyncio
    async def test_update_lead_budget(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_lead: Lead,
    ):
        """Test updating lead budget."""
        response = await client.patch(
            f"/api/leads/{test_lead.id}",
            headers=auth_headers,
            json={
                "budget_amount": 50000.0,
                "budget_currency": "EUR",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["budget_amount"] == 50000.0
        assert data["budget_currency"] == "EUR"


class TestLeadsDelete:
    """Tests for lead delete endpoint."""

    @pytest.mark.asyncio
    async def test_delete_lead_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Test deleting lead."""
        # Create a lead to delete
        lead = Lead(
            first_name="ToDelete",
            last_name="Lead",
            email="delete.lead@example.com",
            status="new",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(lead)
        await db_session.commit()
        await db_session.refresh(lead)
        lead_id = lead.id

        response = await client.delete(
            f"/api/leads/{lead_id}",
            headers=auth_headers,
        )

        assert response.status_code == 204

        # Verify deletion
        result = await db_session.execute(select(Lead).where(Lead.id == lead_id))
        deleted_lead = result.scalar_one_or_none()
        assert deleted_lead is None

    @pytest.mark.asyncio
    async def test_delete_lead_not_found(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test deleting non-existent lead."""
        response = await client.delete(
            "/api/leads/99999",
            headers=auth_headers,
        )

        assert response.status_code == 404


class TestLeadScoring:
    """Tests for lead scoring algorithm."""

    def test_lead_scorer_profile_completeness(self):
        """Test lead scoring based on profile completeness."""
        scorer = LeadScorer()

        # Create a mock lead with complete profile
        class MockLead:
            email = "test@example.com"
            phone = "+1-555-0100"
            mobile = None
            job_title = "CEO"
            first_name = "John"
            last_name = "Doe"
            description = "A lead with description"
            company_name = None
            website = None
            industry = None
            budget_amount = None

        lead = MockLead()
        score, factors = scorer.calculate_score(lead)

        assert factors["profile_completeness"] > 0
        assert factors["profile_completeness"] <= 20

    def test_lead_scorer_budget_tiers(self):
        """Test lead scoring budget tiers."""
        scorer = LeadScorer()

        class MockLead:
            email = "test@example.com"
            phone = None
            mobile = None
            job_title = None
            first_name = "John"
            last_name = "Doe"
            description = None
            company_name = None
            website = None
            industry = None
            budget_amount = None

        # No budget
        lead = MockLead()
        _, factors = scorer.calculate_score(lead)
        assert factors["budget"] == 0

        # Low budget
        lead.budget_amount = 500
        _, factors = scorer.calculate_score(lead)
        assert factors["budget"] == 2

        # Medium budget
        lead.budget_amount = 10000
        _, factors = scorer.calculate_score(lead)
        assert factors["budget"] == 10

        # High budget
        lead.budget_amount = 100000
        _, factors = scorer.calculate_score(lead)
        assert factors["budget"] == 20

    def test_lead_scorer_industry_match(self):
        """Test lead scoring industry matching."""
        scorer = LeadScorer()

        class MockLead:
            email = None
            phone = None
            mobile = None
            job_title = None
            first_name = "John"
            last_name = "Doe"
            description = None
            company_name = None
            website = None
            industry = None
            budget_amount = None

        # No industry
        lead = MockLead()
        _, factors = scorer.calculate_score(lead)
        assert factors["industry"] == 0

        # Priority industry
        lead.industry = "Technology"
        _, factors = scorer.calculate_score(lead)
        assert factors["industry"] == 15

        # Non-priority industry
        lead.industry = "Agriculture"
        _, factors = scorer.calculate_score(lead)
        assert factors["industry"] == 5

    def test_lead_scorer_source_quality(self):
        """Test lead scoring source quality."""
        scorer = LeadScorer()

        class MockLead:
            email = None
            phone = None
            mobile = None
            job_title = None
            first_name = "John"
            last_name = "Doe"
            description = None
            company_name = None
            website = None
            industry = None
            budget_amount = None

        lead = MockLead()

        # No source
        _, factors = scorer.calculate_score(lead, source_name=None)
        assert factors["source_quality"] == 0

        # High quality source
        _, factors = scorer.calculate_score(lead, source_name="Referral")
        assert factors["source_quality"] == 15

        # Medium quality source
        _, factors = scorer.calculate_score(lead, source_name="LinkedIn")
        assert factors["source_quality"] == 10

        # Other source
        _, factors = scorer.calculate_score(lead, source_name="Cold Call")
        assert factors["source_quality"] == 5

    def test_calculate_lead_score_function(self):
        """Test the convenience calculate_lead_score function."""

        class MockLead:
            email = "test@example.com"
            phone = "+1-555-0100"
            mobile = None
            job_title = "CEO"
            first_name = "John"
            last_name = "Doe"
            description = "A lead"
            company_name = "Test Corp"
            website = "https://test.com"
            industry = "Technology"
            budget_amount = 50000

        lead = MockLead()
        score, factors_json = calculate_lead_score(lead, "Referral")

        assert isinstance(score, int)
        assert score > 0
        assert isinstance(factors_json, str)
        # Should be valid JSON
        import json

        factors = json.loads(factors_json)
        assert "profile_completeness" in factors
        assert "budget" in factors


class TestLeadSources:
    """Tests for lead sources endpoints."""

    @pytest.mark.asyncio
    async def test_list_sources(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_lead_source: LeadSource,
    ):
        """Test listing lead sources."""
        response = await client.get(
            "/api/leads/sources/",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert any(s["id"] == test_lead_source.id for s in data)

    @pytest.mark.asyncio
    async def test_create_source(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test creating a lead source."""
        response = await client.post(
            "/api/leads/sources/",
            headers=auth_headers,
            json={
                "name": "Trade Show",
                "description": "Leads from trade shows",
                "is_active": True,
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Trade Show"
        assert data["is_active"] is True


class TestLeadsUnauthorized:
    """Tests for unauthorized access to leads endpoints."""

    @pytest.mark.asyncio
    async def test_list_leads_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test listing leads without auth fails."""
        response = await client.get("/api/leads")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_create_lead_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test creating lead without auth fails."""
        response = await client.post(
            "/api/leads",
            json={"first_name": "Test", "last_name": "Lead"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_lead_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession, test_lead: Lead
    ):
        """Test getting lead without auth fails."""
        response = await client.get(f"/api/leads/{test_lead.id}")
        assert response.status_code == 401
