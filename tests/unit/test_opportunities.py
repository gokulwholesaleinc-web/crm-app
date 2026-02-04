"""
Unit tests for opportunities and pipeline stages CRUD endpoints.

Tests for list, create, get, update, delete, and pipeline stage operations.
"""

import pytest
from datetime import date, timedelta
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.auth.models import User
from src.opportunities.models import Opportunity, PipelineStage
from src.contacts.models import Contact
from src.companies.models import Company


class TestPipelineStages:
    """Tests for pipeline stages endpoints."""

    @pytest.mark.asyncio
    async def test_list_stages(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_pipeline_stage: PipelineStage,
    ):
        """Test listing pipeline stages."""
        response = await client.get(
            "/api/opportunities/stages",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert any(s["id"] == test_pipeline_stage.id for s in data)

    @pytest.mark.asyncio
    async def test_list_stages_active_only(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_pipeline_stage: PipelineStage,
    ):
        """Test listing only active pipeline stages."""
        # Create an inactive stage
        inactive_stage = PipelineStage(
            name="Inactive Stage",
            order=99,
            is_active=False,
        )
        db_session.add(inactive_stage)
        await db_session.commit()

        response = await client.get(
            "/api/opportunities/stages",
            headers=auth_headers,
            params={"active_only": True},
        )

        assert response.status_code == 200
        data = response.json()
        assert all(s["is_active"] for s in data)

    @pytest.mark.asyncio
    async def test_create_stage(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test creating a pipeline stage."""
        response = await client.post(
            "/api/opportunities/stages",
            headers=auth_headers,
            json={
                "name": "Negotiation",
                "description": "Negotiating terms",
                "order": 3,
                "color": "#f59e0b",
                "probability": 60,
                "is_won": False,
                "is_lost": False,
                "is_active": True,
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Negotiation"
        assert data["probability"] == 60
        assert data["color"] == "#f59e0b"

    @pytest.mark.asyncio
    async def test_create_won_stage(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test creating a won stage."""
        response = await client.post(
            "/api/opportunities/stages",
            headers=auth_headers,
            json={
                "name": "Closed Won",
                "description": "Deal won",
                "order": 10,
                "probability": 100,
                "is_won": True,
                "is_lost": False,
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["is_won"] is True
        assert data["probability"] == 100

    @pytest.mark.asyncio
    async def test_create_lost_stage(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test creating a lost stage."""
        response = await client.post(
            "/api/opportunities/stages",
            headers=auth_headers,
            json={
                "name": "Closed Lost",
                "description": "Deal lost",
                "order": 11,
                "probability": 0,
                "is_won": False,
                "is_lost": True,
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["is_lost"] is True
        assert data["probability"] == 0

    @pytest.mark.asyncio
    async def test_update_stage(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_pipeline_stage: PipelineStage,
    ):
        """Test updating a pipeline stage."""
        response = await client.patch(
            f"/api/opportunities/stages/{test_pipeline_stage.id}",
            headers=auth_headers,
            json={
                "name": "Updated Stage",
                "probability": 50,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Stage"
        assert data["probability"] == 50

    @pytest.mark.asyncio
    async def test_update_stage_not_found(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test updating non-existent stage."""
        response = await client.patch(
            "/api/opportunities/stages/99999",
            headers=auth_headers,
            json={"name": "Test"},
        )

        assert response.status_code == 404


class TestOpportunitiesList:
    """Tests for opportunities list endpoint with pagination."""

    @pytest.mark.asyncio
    async def test_list_opportunities_empty(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_pipeline_stage: PipelineStage,
    ):
        """Test listing opportunities when none exist."""
        response = await client.get("/api/opportunities", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["page"] == 1

    @pytest.mark.asyncio
    async def test_list_opportunities_with_data(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_opportunity: Opportunity,
    ):
        """Test listing opportunities with existing data."""
        response = await client.get("/api/opportunities", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        assert len(data["items"]) >= 1
        assert any(o["id"] == test_opportunity.id for o in data["items"])

    @pytest.mark.asyncio
    async def test_list_opportunities_pagination(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_pipeline_stage: PipelineStage,
    ):
        """Test opportunities pagination."""
        # Create multiple opportunities
        for i in range(15):
            opp = Opportunity(
                name=f"Opportunity {i}",
                pipeline_stage_id=test_pipeline_stage.id,
                amount=10000.0 * (i + 1),
                owner_id=test_user.id,
                created_by_id=test_user.id,
            )
            db_session.add(opp)
        await db_session.commit()

        # First page
        response = await client.get(
            "/api/opportunities",
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
            "/api/opportunities",
            headers=auth_headers,
            params={"page": 2, "page_size": 10},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 5

    @pytest.mark.asyncio
    async def test_list_opportunities_filter_by_stage(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_opportunity: Opportunity,
        test_pipeline_stage: PipelineStage,
    ):
        """Test filtering opportunities by pipeline stage."""
        response = await client.get(
            "/api/opportunities",
            headers=auth_headers,
            params={"pipeline_stage_id": test_pipeline_stage.id},
        )

        assert response.status_code == 200
        data = response.json()
        assert all(
            o["pipeline_stage_id"] == test_pipeline_stage.id for o in data["items"]
        )

    @pytest.mark.asyncio
    async def test_list_opportunities_filter_by_company(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_opportunity: Opportunity,
        test_company: Company,
    ):
        """Test filtering opportunities by company."""
        response = await client.get(
            "/api/opportunities",
            headers=auth_headers,
            params={"company_id": test_company.id},
        )

        assert response.status_code == 200
        data = response.json()
        assert all(o["company_id"] == test_company.id for o in data["items"])

    @pytest.mark.asyncio
    async def test_list_opportunities_search(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_opportunity: Opportunity,
    ):
        """Test searching opportunities."""
        response = await client.get(
            "/api/opportunities",
            headers=auth_headers,
            params={"search": test_opportunity.name},
        )

        assert response.status_code == 200
        data = response.json()
        assert any(o["id"] == test_opportunity.id for o in data["items"])


class TestOpportunitiesCreate:
    """Tests for opportunity creation endpoint."""

    @pytest.mark.asyncio
    async def test_create_opportunity_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_pipeline_stage: PipelineStage,
        test_contact: Contact,
        test_company: Company,
    ):
        """Test successful opportunity creation."""
        response = await client.post(
            "/api/opportunities",
            headers=auth_headers,
            json={
                "name": "New Deal",
                "description": "A promising new deal",
                "pipeline_stage_id": test_pipeline_stage.id,
                "amount": 75000.0,
                "currency": "USD",
                "expected_close_date": (date.today() + timedelta(days=60)).isoformat(),
                "contact_id": test_contact.id,
                "company_id": test_company.id,
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "New Deal"
        assert data["amount"] == 75000.0
        assert data["pipeline_stage_id"] == test_pipeline_stage.id
        assert "id" in data
        assert "weighted_amount" in data

    @pytest.mark.asyncio
    async def test_create_opportunity_minimal(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_pipeline_stage: PipelineStage,
    ):
        """Test creating opportunity with minimal required fields."""
        response = await client.post(
            "/api/opportunities",
            headers=auth_headers,
            json={
                "name": "Minimal Deal",
                "pipeline_stage_id": test_pipeline_stage.id,
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Minimal Deal"
        assert data["currency"] == "USD"  # Default

    @pytest.mark.asyncio
    async def test_create_opportunity_missing_name(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_pipeline_stage: PipelineStage,
    ):
        """Test creating opportunity without name fails."""
        response = await client.post(
            "/api/opportunities",
            headers=auth_headers,
            json={
                "pipeline_stage_id": test_pipeline_stage.id,
                "amount": 50000.0,
            },
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_opportunity_missing_stage(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test creating opportunity without pipeline stage fails."""
        response = await client.post(
            "/api/opportunities",
            headers=auth_headers,
            json={
                "name": "No Stage Deal",
                "amount": 50000.0,
            },
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_opportunity_with_probability_override(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_pipeline_stage: PipelineStage,
    ):
        """Test creating opportunity with custom probability."""
        response = await client.post(
            "/api/opportunities",
            headers=auth_headers,
            json={
                "name": "Custom Probability Deal",
                "pipeline_stage_id": test_pipeline_stage.id,
                "amount": 100000.0,
                "probability": 75,
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["probability"] == 75
        # Weighted amount should use custom probability
        assert data["weighted_amount"] == 75000.0


class TestOpportunitiesGetById:
    """Tests for get opportunity by ID endpoint."""

    @pytest.mark.asyncio
    async def test_get_opportunity_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_opportunity: Opportunity,
    ):
        """Test getting opportunity by ID."""
        response = await client.get(
            f"/api/opportunities/{test_opportunity.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == test_opportunity.id
        assert data["name"] == test_opportunity.name
        assert data["amount"] == test_opportunity.amount

    @pytest.mark.asyncio
    async def test_get_opportunity_not_found(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test getting non-existent opportunity."""
        response = await client.get(
            "/api/opportunities/99999",
            headers=auth_headers,
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_get_opportunity_includes_relationships(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_opportunity: Opportunity,
        test_pipeline_stage: PipelineStage,
        test_contact: Contact,
        test_company: Company,
    ):
        """Test that getting opportunity includes related data."""
        response = await client.get(
            f"/api/opportunities/{test_opportunity.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()

        # Pipeline stage
        assert data["pipeline_stage"] is not None
        assert data["pipeline_stage"]["id"] == test_pipeline_stage.id

        # Contact
        assert data["contact"] is not None
        assert data["contact"]["id"] == test_contact.id

        # Company
        assert data["company"] is not None
        assert data["company"]["id"] == test_company.id


class TestOpportunitiesUpdate:
    """Tests for opportunity update endpoint."""

    @pytest.mark.asyncio
    async def test_update_opportunity_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_opportunity: Opportunity,
    ):
        """Test updating opportunity."""
        response = await client.patch(
            f"/api/opportunities/{test_opportunity.id}",
            headers=auth_headers,
            json={
                "name": "Updated Deal Name",
                "amount": 100000.0,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Deal Name"
        assert data["amount"] == 100000.0

    @pytest.mark.asyncio
    async def test_update_opportunity_not_found(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test updating non-existent opportunity."""
        response = await client.patch(
            "/api/opportunities/99999",
            headers=auth_headers,
            json={"name": "Test"},
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_opportunity_stage(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_opportunity: Opportunity,
        test_won_stage: PipelineStage,
    ):
        """Test updating opportunity stage."""
        response = await client.patch(
            f"/api/opportunities/{test_opportunity.id}",
            headers=auth_headers,
            json={"pipeline_stage_id": test_won_stage.id},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["pipeline_stage_id"] == test_won_stage.id

    @pytest.mark.asyncio
    async def test_update_opportunity_close_date(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_opportunity: Opportunity,
    ):
        """Test updating opportunity expected close date."""
        new_date = (date.today() + timedelta(days=90)).isoformat()
        response = await client.patch(
            f"/api/opportunities/{test_opportunity.id}",
            headers=auth_headers,
            json={"expected_close_date": new_date},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["expected_close_date"] == new_date

    @pytest.mark.asyncio
    async def test_update_opportunity_loss_reason(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_opportunity: Opportunity,
    ):
        """Test updating opportunity with loss reason."""
        response = await client.patch(
            f"/api/opportunities/{test_opportunity.id}",
            headers=auth_headers,
            json={
                "loss_reason": "Budget constraints",
                "loss_notes": "Client decided to postpone the project",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["loss_reason"] == "Budget constraints"
        assert data["loss_notes"] == "Client decided to postpone the project"


class TestOpportunitiesDelete:
    """Tests for opportunity delete endpoint."""

    @pytest.mark.asyncio
    async def test_delete_opportunity_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_pipeline_stage: PipelineStage,
    ):
        """Test deleting opportunity."""
        # Create an opportunity to delete
        opp = Opportunity(
            name="To Delete Deal",
            pipeline_stage_id=test_pipeline_stage.id,
            amount=25000.0,
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(opp)
        await db_session.commit()
        await db_session.refresh(opp)
        opp_id = opp.id

        response = await client.delete(
            f"/api/opportunities/{opp_id}",
            headers=auth_headers,
        )

        assert response.status_code == 204

        # Verify deletion
        result = await db_session.execute(
            select(Opportunity).where(Opportunity.id == opp_id)
        )
        deleted_opp = result.scalar_one_or_none()
        assert deleted_opp is None

    @pytest.mark.asyncio
    async def test_delete_opportunity_not_found(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test deleting non-existent opportunity."""
        response = await client.delete(
            "/api/opportunities/99999",
            headers=auth_headers,
        )

        assert response.status_code == 404


class TestMoveOpportunity:
    """Tests for moving opportunity between stages."""

    @pytest.mark.asyncio
    async def test_move_opportunity_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_opportunity: Opportunity,
        test_won_stage: PipelineStage,
    ):
        """Test moving opportunity to new stage."""
        response = await client.post(
            f"/api/opportunities/{test_opportunity.id}/move",
            headers=auth_headers,
            json={"new_stage_id": test_won_stage.id},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["pipeline_stage_id"] == test_won_stage.id

    @pytest.mark.asyncio
    async def test_move_opportunity_not_found(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_pipeline_stage: PipelineStage,
    ):
        """Test moving non-existent opportunity."""
        response = await client.post(
            "/api/opportunities/99999/move",
            headers=auth_headers,
            json={"new_stage_id": test_pipeline_stage.id},
        )

        assert response.status_code == 404


class TestKanbanView:
    """Tests for kanban/pipeline view endpoint."""

    @pytest.mark.asyncio
    async def test_get_kanban_view(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_opportunity: Opportunity,
        test_pipeline_stage: PipelineStage,
    ):
        """Test getting kanban view."""
        response = await client.get(
            "/api/opportunities/kanban",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "stages" in data
        assert isinstance(data["stages"], list)

    @pytest.mark.asyncio
    async def test_get_kanban_view_filter_by_owner(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_opportunity: Opportunity,
        test_user: User,
    ):
        """Test getting kanban view filtered by owner."""
        response = await client.get(
            "/api/opportunities/kanban",
            headers=auth_headers,
            params={"owner_id": test_user.id},
        )

        assert response.status_code == 200
        data = response.json()
        assert "stages" in data


class TestWeightedAmount:
    """Tests for weighted amount calculation."""

    @pytest.mark.asyncio
    async def test_weighted_amount_calculation(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_pipeline_stage: PipelineStage,
    ):
        """Test weighted amount is calculated correctly."""
        # Create opportunity with known values
        response = await client.post(
            "/api/opportunities",
            headers=auth_headers,
            json={
                "name": "Weighted Test",
                "pipeline_stage_id": test_pipeline_stage.id,
                "amount": 100000.0,
            },
        )

        assert response.status_code == 201
        data = response.json()
        # Stage probability is 20%, so weighted should be 20000
        assert data["weighted_amount"] == 20000.0

    @pytest.mark.asyncio
    async def test_weighted_amount_with_override(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_pipeline_stage: PipelineStage,
    ):
        """Test weighted amount with probability override."""
        response = await client.post(
            "/api/opportunities",
            headers=auth_headers,
            json={
                "name": "Override Test",
                "pipeline_stage_id": test_pipeline_stage.id,
                "amount": 100000.0,
                "probability": 50,  # Override stage probability
            },
        )

        assert response.status_code == 201
        data = response.json()
        # Custom probability is 50%, so weighted should be 50000
        assert data["weighted_amount"] == 50000.0


class TestOpportunitiesUnauthorized:
    """Tests for unauthorized access to opportunities endpoints."""

    @pytest.mark.asyncio
    async def test_list_opportunities_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test listing opportunities without auth fails."""
        response = await client.get("/api/opportunities")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_create_opportunity_unauthorized(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_pipeline_stage: PipelineStage,
    ):
        """Test creating opportunity without auth fails."""
        response = await client.post(
            "/api/opportunities",
            json={
                "name": "Test",
                "pipeline_stage_id": test_pipeline_stage.id,
            },
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_opportunity_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession, test_opportunity: Opportunity
    ):
        """Test getting opportunity without auth fails."""
        response = await client.get(f"/api/opportunities/{test_opportunity.id}")
        assert response.status_code == 401
