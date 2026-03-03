"""
Unit tests for Lead Pipeline Stages and Kanban board.

Tests the pipeline_stage_id field on leads, pipeline-stages endpoint,
kanban board endpoint, lead move endpoint, and pipeline_type isolation.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.leads.models import Lead, LeadSource
from src.opportunities.models import PipelineStage


@pytest_asyncio.fixture
async def lead_pipeline_stages(db_session: AsyncSession) -> list[PipelineStage]:
    """Create lead-type pipeline stages for testing."""
    stages_data = [
        {"name": "New", "order": 1, "color": "#3b82f6", "probability": 10, "is_won": False, "is_lost": False},
        {"name": "Discovery", "order": 2, "color": "#8b5cf6", "probability": 25, "is_won": False, "is_lost": False},
        {"name": "Qualified", "order": 3, "color": "#f59e0b", "probability": 50, "is_won": False, "is_lost": False},
        {"name": "Won", "order": 7, "color": "#22c55e", "probability": 100, "is_won": True, "is_lost": False},
        {"name": "Lost", "order": 8, "color": "#ef4444", "probability": 0, "is_won": False, "is_lost": True},
    ]
    stages = []
    for data in stages_data:
        stage = PipelineStage(
            pipeline_type="lead",
            is_active=True,
            **data,
        )
        db_session.add(stage)
        stages.append(stage)
    await db_session.commit()
    for s in stages:
        await db_session.refresh(s)
    return stages


@pytest_asyncio.fixture
async def opp_pipeline_stage(db_session: AsyncSession) -> PipelineStage:
    """Create an opportunity-type pipeline stage for isolation tests."""
    stage = PipelineStage(
        name="Opp Discovery",
        order=1,
        color="#6366f1",
        probability=20,
        is_won=False,
        is_lost=False,
        is_active=True,
        pipeline_type="opportunity",
    )
    db_session.add(stage)
    await db_session.commit()
    await db_session.refresh(stage)
    return stage


class TestLeadPipelineStages:
    """Tests for lead pipeline stage endpoints."""

    @pytest.mark.asyncio
    async def test_get_lead_pipeline_stages(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_user: User,
        lead_pipeline_stages: list[PipelineStage],
    ):
        """GET /api/leads/pipeline-stages returns only lead-type stages."""
        response = await client.get(
            "/api/leads/pipeline-stages",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 5
        assert data[0]["name"] == "New"
        assert data[1]["name"] == "Discovery"

    @pytest.mark.asyncio
    async def test_pipeline_stages_excludes_opportunity_stages(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_user: User,
        lead_pipeline_stages: list[PipelineStage],
        opp_pipeline_stage: PipelineStage,
    ):
        """Lead pipeline-stages endpoint does not return opportunity stages."""
        response = await client.get(
            "/api/leads/pipeline-stages",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        stage_names = [s["name"] for s in data]
        assert "Opp Discovery" not in stage_names
        assert len(data) == 5

    @pytest.mark.asyncio
    async def test_pipeline_stages_ordered(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_user: User,
        lead_pipeline_stages: list[PipelineStage],
    ):
        """Pipeline stages are returned in order."""
        response = await client.get(
            "/api/leads/pipeline-stages",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        orders = [s["order"] for s in data]
        assert orders == sorted(orders)


class TestCreateLeadWithPipelineStage:
    """Tests for creating leads with a pipeline_stage_id."""

    @pytest.mark.asyncio
    async def test_create_lead_with_pipeline_stage(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_user: User,
        lead_pipeline_stages: list[PipelineStage],
    ):
        """Creating a lead with pipeline_stage_id sets the field."""
        stage = lead_pipeline_stages[0]  # "New" stage
        response = await client.post(
            "/api/leads",
            headers=auth_headers,
            json={
                "first_name": "Pipeline",
                "last_name": "Lead",
                "email": "pipeline.lead@example.com",
                "status": "new",
                "pipeline_stage_id": stage.id,
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["pipeline_stage_id"] == stage.id
        assert data["pipeline_stage"]["name"] == "New"

    @pytest.mark.asyncio
    async def test_create_lead_without_pipeline_stage(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_user: User,
    ):
        """Creating a lead without pipeline_stage_id defaults to null."""
        response = await client.post(
            "/api/leads",
            headers=auth_headers,
            json={
                "first_name": "No",
                "last_name": "Stage",
                "email": "no.stage@example.com",
                "status": "new",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["pipeline_stage_id"] is None
        assert data["pipeline_stage"] is None

    @pytest.mark.asyncio
    async def test_update_lead_pipeline_stage(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        lead_pipeline_stages: list[PipelineStage],
    ):
        """Updating a lead's pipeline_stage_id works."""
        # Create lead first
        lead = Lead(
            first_name="Update",
            last_name="Stage",
            email="update.stage@example.com",
            status="new",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(lead)
        await db_session.commit()
        await db_session.refresh(lead)

        discovery_stage = lead_pipeline_stages[1]  # "Discovery"
        response = await client.patch(
            f"/api/leads/{lead.id}",
            headers=auth_headers,
            json={"pipeline_stage_id": discovery_stage.id},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["pipeline_stage_id"] == discovery_stage.id
        assert data["pipeline_stage"]["name"] == "Discovery"


class TestLeadKanban:
    """Tests for the lead Kanban board endpoint."""

    @pytest.mark.asyncio
    async def test_kanban_returns_stages(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_user: User,
        lead_pipeline_stages: list[PipelineStage],
    ):
        """GET /api/leads/kanban returns all lead pipeline stages."""
        response = await client.get(
            "/api/leads/kanban",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "stages" in data
        assert len(data["stages"]) == 5

    @pytest.mark.asyncio
    async def test_kanban_shows_leads_in_stages(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        lead_pipeline_stages: list[PipelineStage],
    ):
        """Kanban shows leads assigned to their pipeline stages."""
        new_stage = lead_pipeline_stages[0]
        discovery_stage = lead_pipeline_stages[1]

        # Create leads in different stages
        lead1 = Lead(
            first_name="Alice",
            last_name="New",
            email="alice@example.com",
            status="new",
            score=80,
            pipeline_stage_id=new_stage.id,
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        lead2 = Lead(
            first_name="Bob",
            last_name="Discovery",
            email="bob@example.com",
            status="contacted",
            score=60,
            pipeline_stage_id=discovery_stage.id,
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add_all([lead1, lead2])
        await db_session.commit()

        response = await client.get(
            "/api/leads/kanban",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()

        stages_map = {s["stage_name"]: s for s in data["stages"]}
        assert stages_map["New"]["count"] == 1
        assert stages_map["New"]["leads"][0]["full_name"] == "Alice New"
        assert stages_map["Discovery"]["count"] == 1
        assert stages_map["Discovery"]["leads"][0]["full_name"] == "Bob Discovery"

    @pytest.mark.asyncio
    async def test_kanban_empty_stages(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_user: User,
        lead_pipeline_stages: list[PipelineStage],
    ):
        """Kanban returns empty lead lists for stages with no leads."""
        response = await client.get(
            "/api/leads/kanban",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        for stage in data["stages"]:
            assert stage["count"] == 0
            assert stage["leads"] == []


class TestMoveLeadStage:
    """Tests for the lead move endpoint."""

    @pytest.mark.asyncio
    async def test_move_lead_to_new_stage(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        lead_pipeline_stages: list[PipelineStage],
    ):
        """POST /api/leads/{id}/move updates pipeline_stage_id."""
        new_stage = lead_pipeline_stages[0]
        discovery_stage = lead_pipeline_stages[1]

        lead = Lead(
            first_name="Move",
            last_name="Test",
            email="move.test@example.com",
            status="new",
            pipeline_stage_id=new_stage.id,
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(lead)
        await db_session.commit()
        await db_session.refresh(lead)

        response = await client.post(
            f"/api/leads/{lead.id}/move",
            headers=auth_headers,
            json={"new_stage_id": discovery_stage.id},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["pipeline_stage_id"] == discovery_stage.id

    @pytest.mark.asyncio
    async def test_move_lead_to_won_syncs_status(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        lead_pipeline_stages: list[PipelineStage],
    ):
        """Moving lead to a won stage sets status to 'converted'."""
        new_stage = lead_pipeline_stages[0]
        won_stage = lead_pipeline_stages[3]  # "Won" stage

        lead = Lead(
            first_name="Win",
            last_name="Lead",
            email="win.lead@example.com",
            status="new",
            pipeline_stage_id=new_stage.id,
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(lead)
        await db_session.commit()
        await db_session.refresh(lead)

        response = await client.post(
            f"/api/leads/{lead.id}/move",
            headers=auth_headers,
            json={"new_stage_id": won_stage.id},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "converted"
        assert data["pipeline_stage_id"] == won_stage.id

    @pytest.mark.asyncio
    async def test_move_lead_to_lost_syncs_status(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        lead_pipeline_stages: list[PipelineStage],
    ):
        """Moving lead to a lost stage sets status to 'lost'."""
        new_stage = lead_pipeline_stages[0]
        lost_stage = lead_pipeline_stages[4]  # "Lost" stage

        lead = Lead(
            first_name="Lose",
            last_name="Lead",
            email="lose.lead@example.com",
            status="new",
            pipeline_stage_id=new_stage.id,
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(lead)
        await db_session.commit()
        await db_session.refresh(lead)

        response = await client.post(
            f"/api/leads/{lead.id}/move",
            headers=auth_headers,
            json={"new_stage_id": lost_stage.id},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "lost"
        assert data["pipeline_stage_id"] == lost_stage.id

    @pytest.mark.asyncio
    async def test_move_lead_status_sync_by_order(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        lead_pipeline_stages: list[PipelineStage],
    ):
        """Moving to a regular stage syncs status by order mapping."""
        new_stage = lead_pipeline_stages[0]
        # Discovery stage has order=2, should map to "contacted"
        discovery_stage = lead_pipeline_stages[1]

        lead = Lead(
            first_name="Order",
            last_name="Map",
            email="order.map@example.com",
            status="new",
            pipeline_stage_id=new_stage.id,
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(lead)
        await db_session.commit()
        await db_session.refresh(lead)

        response = await client.post(
            f"/api/leads/{lead.id}/move",
            headers=auth_headers,
            json={"new_stage_id": discovery_stage.id},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "contacted"

    @pytest.mark.asyncio
    async def test_move_lead_to_nonexistent_stage(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        lead_pipeline_stages: list[PipelineStage],
    ):
        """Moving lead to a non-existent stage returns 404."""
        new_stage = lead_pipeline_stages[0]

        lead = Lead(
            first_name="Bad",
            last_name="Move",
            email="bad.move@example.com",
            status="new",
            pipeline_stage_id=new_stage.id,
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(lead)
        await db_session.commit()
        await db_session.refresh(lead)

        response = await client.post(
            f"/api/leads/{lead.id}/move",
            headers=auth_headers,
            json={"new_stage_id": 99999},
        )
        assert response.status_code == 404


class TestPipelineTypeIsolation:
    """Tests ensuring lead and opportunity pipeline stages are isolated."""

    @pytest.mark.asyncio
    async def test_opportunity_stages_exclude_lead_stages(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_user: User,
        lead_pipeline_stages: list[PipelineStage],
        opp_pipeline_stage: PipelineStage,
    ):
        """GET /api/opportunities/stages only returns opportunity stages."""
        response = await client.get(
            "/api/opportunities/stages",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        stage_names = [s["name"] for s in data]
        assert "Opp Discovery" in stage_names
        # Lead stage names should not appear
        assert "New" not in stage_names
        assert "Discovery" not in stage_names

    @pytest.mark.asyncio
    async def test_backward_compatibility_status_still_works(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_user: User,
    ):
        """Lead status field still works without pipeline_stage_id."""
        response = await client.post(
            "/api/leads",
            headers=auth_headers,
            json={
                "first_name": "Backward",
                "last_name": "Compat",
                "email": "backward.compat@example.com",
                "status": "qualified",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "qualified"
        assert data["pipeline_stage_id"] is None

    @pytest.mark.asyncio
    async def test_lead_pipeline_stage_in_get_response(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        lead_pipeline_stages: list[PipelineStage],
    ):
        """GET /api/leads/{id} includes pipeline_stage details."""
        stage = lead_pipeline_stages[2]  # "Qualified"
        lead = Lead(
            first_name="Detail",
            last_name="Check",
            email="detail.check@example.com",
            status="qualified",
            pipeline_stage_id=stage.id,
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(lead)
        await db_session.commit()
        await db_session.refresh(lead)

        response = await client.get(
            f"/api/leads/{lead.id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["pipeline_stage_id"] == stage.id
        assert data["pipeline_stage"]["name"] == "Qualified"
        assert data["pipeline_stage"]["probability"] == 50
        assert data["pipeline_stage"]["color"] == "#f59e0b"
