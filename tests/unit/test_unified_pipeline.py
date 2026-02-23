"""
Unit tests for Unified Pipeline View.

Tests auto-conversion when moving a lead to a Won stage,
the unified pipeline endpoint returning both lead and opportunity stages,
and that conversion uses the first opportunity pipeline stage.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.leads.models import Lead
from src.opportunities.models import PipelineStage, Opportunity


@pytest_asyncio.fixture
async def lead_stages(db_session: AsyncSession) -> list[PipelineStage]:
    """Create lead-type pipeline stages."""
    stages_data = [
        {"name": "New", "order": 1, "color": "#3b82f6", "probability": 10, "is_won": False, "is_lost": False},
        {"name": "Discovery", "order": 2, "color": "#8b5cf6", "probability": 25, "is_won": False, "is_lost": False},
        {"name": "Qualified", "order": 3, "color": "#f59e0b", "probability": 50, "is_won": False, "is_lost": False},
        {"name": "Won", "order": 7, "color": "#22c55e", "probability": 100, "is_won": True, "is_lost": False},
        {"name": "Lost", "order": 8, "color": "#ef4444", "probability": 0, "is_won": False, "is_lost": True},
    ]
    stages = []
    for data in stages_data:
        stage = PipelineStage(pipeline_type="lead", is_active=True, **data)
        db_session.add(stage)
        stages.append(stage)
    await db_session.commit()
    for s in stages:
        await db_session.refresh(s)
    return stages


@pytest_asyncio.fixture
async def opp_stages(db_session: AsyncSession) -> list[PipelineStage]:
    """Create opportunity-type pipeline stages."""
    stages_data = [
        {"name": "Qualification", "order": 1, "color": "#6366f1", "probability": 20, "is_won": False, "is_lost": False},
        {"name": "Proposal", "order": 2, "color": "#8b5cf6", "probability": 50, "is_won": False, "is_lost": False},
        {"name": "Negotiation", "order": 3, "color": "#f59e0b", "probability": 75, "is_won": False, "is_lost": False},
        {"name": "Closed Won", "order": 4, "color": "#22c55e", "probability": 100, "is_won": True, "is_lost": False},
        {"name": "Closed Lost", "order": 5, "color": "#ef4444", "probability": 0, "is_won": False, "is_lost": True},
    ]
    stages = []
    for data in stages_data:
        stage = PipelineStage(pipeline_type="opportunity", is_active=True, **data)
        db_session.add(stage)
        stages.append(stage)
    await db_session.commit()
    for s in stages:
        await db_session.refresh(s)
    return stages


@pytest_asyncio.fixture
async def test_lead_in_pipeline(
    db_session: AsyncSession,
    test_user: User,
    lead_stages: list[PipelineStage],
) -> Lead:
    """Create a lead in the 'New' stage."""
    lead = Lead(
        first_name="Pipeline",
        last_name="Lead",
        email="pipeline.lead@example.com",
        company_name="Acme Corp",
        status="new",
        score=75,
        pipeline_stage_id=lead_stages[0].id,
        budget_amount=10000.0,
        budget_currency="USD",
        owner_id=test_user.id,
        created_by_id=test_user.id,
    )
    db_session.add(lead)
    await db_session.commit()
    await db_session.refresh(lead)
    return lead


class TestAutoConversion:
    """Tests for auto-conversion when moving a lead to a Won stage."""

    @pytest.mark.asyncio
    async def test_move_lead_to_won_auto_converts(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        lead_stages: list[PipelineStage],
        opp_stages: list[PipelineStage],
        test_lead_in_pipeline: Lead,
    ):
        """Moving a lead to a Won stage auto-creates Contact + Opportunity."""
        won_stage = lead_stages[3]  # "Won" stage

        response = await client.post(
            f"/api/leads/{test_lead_in_pipeline.id}/move",
            headers=auth_headers,
            json={"new_stage_id": won_stage.id},
        )
        assert response.status_code == 200
        data = response.json()

        # Lead should be converted
        assert data["status"] == "converted"
        assert data["pipeline_stage_id"] == won_stage.id

        # Conversion info should be present
        assert "conversion" in data
        assert data["conversion"]["converted"] is True
        assert data["conversion"]["contact_id"] is not None
        assert data["conversion"]["opportunity_id"] is not None

    @pytest.mark.asyncio
    async def test_auto_conversion_uses_first_opp_stage(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        lead_stages: list[PipelineStage],
        opp_stages: list[PipelineStage],
        test_lead_in_pipeline: Lead,
    ):
        """Auto-conversion places the opportunity in the first opportunity pipeline stage."""
        from sqlalchemy import select

        won_stage = lead_stages[3]
        first_opp_stage = opp_stages[0]  # "Qualification" (order=1)

        response = await client.post(
            f"/api/leads/{test_lead_in_pipeline.id}/move",
            headers=auth_headers,
            json={"new_stage_id": won_stage.id},
        )
        assert response.status_code == 200
        data = response.json()

        opp_id = data["conversion"]["opportunity_id"]

        # Verify the opportunity is in the first opp stage
        result = await db_session.execute(
            select(Opportunity).where(Opportunity.id == opp_id)
        )
        opportunity = result.scalar_one()
        assert opportunity.pipeline_stage_id == first_opp_stage.id

    @pytest.mark.asyncio
    async def test_auto_conversion_creates_company_when_company_name_present(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        lead_stages: list[PipelineStage],
        opp_stages: list[PipelineStage],
        test_lead_in_pipeline: Lead,
    ):
        """Auto-conversion creates a company when lead has company_name."""
        won_stage = lead_stages[3]

        response = await client.post(
            f"/api/leads/{test_lead_in_pipeline.id}/move",
            headers=auth_headers,
            json={"new_stage_id": won_stage.id},
        )
        assert response.status_code == 200
        data = response.json()

        # company_id should be set because lead has company_name
        assert data["conversion"]["company_id"] is not None

    @pytest.mark.asyncio
    async def test_no_conversion_if_already_converted(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        lead_stages: list[PipelineStage],
        opp_stages: list[PipelineStage],
    ):
        """Moving an already-converted lead to Won does not re-convert."""
        new_stage = lead_stages[0]
        won_stage = lead_stages[3]

        # Create a lead that's already been converted
        lead = Lead(
            first_name="Already",
            last_name="Converted",
            email="already.converted@example.com",
            status="qualified",
            pipeline_stage_id=new_stage.id,
            converted_contact_id=999,  # already converted
            converted_opportunity_id=888,
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

        # Should not have conversion info
        assert "conversion" not in data or data.get("conversion") is None

    @pytest.mark.asyncio
    async def test_no_conversion_when_no_opp_stages(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        lead_stages: list[PipelineStage],
        # Note: NOT using opp_stages fixture - no opportunity stages exist
    ):
        """Moving to Won without opportunity stages does not crash."""
        new_stage = lead_stages[0]
        won_stage = lead_stages[3]

        lead = Lead(
            first_name="No",
            last_name="OppStages",
            email="no.oppstages@example.com",
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
        # No conversion because there are no opportunity stages
        assert "conversion" not in data or data.get("conversion") is None


class TestUnifiedPipelineEndpoint:
    """Tests for the GET /api/dashboard/pipeline/unified endpoint."""

    @pytest.mark.asyncio
    async def test_unified_returns_both_sections(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_user: User,
        lead_stages: list[PipelineStage],
        opp_stages: list[PipelineStage],
    ):
        """Unified pipeline returns both lead_stages and opportunity_stages."""
        response = await client.get(
            "/api/dashboard/pipeline/unified",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "lead_stages" in data
        assert "opportunity_stages" in data
        assert len(data["lead_stages"]) == 5
        assert len(data["opportunity_stages"]) == 5

    @pytest.mark.asyncio
    async def test_unified_lead_stages_have_correct_entity_type(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_user: User,
        lead_stages: list[PipelineStage],
        opp_stages: list[PipelineStage],
    ):
        """Lead stages in unified view have entity_type='lead'."""
        response = await client.get(
            "/api/dashboard/pipeline/unified",
            headers=auth_headers,
        )
        data = response.json()
        for stage in data["lead_stages"]:
            assert stage["entity_type"] == "lead"

    @pytest.mark.asyncio
    async def test_unified_opp_stages_have_correct_entity_type(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_user: User,
        lead_stages: list[PipelineStage],
        opp_stages: list[PipelineStage],
    ):
        """Opportunity stages in unified view have entity_type='opportunity'."""
        response = await client.get(
            "/api/dashboard/pipeline/unified",
            headers=auth_headers,
        )
        data = response.json()
        for stage in data["opportunity_stages"]:
            assert stage["entity_type"] == "opportunity"

    @pytest.mark.asyncio
    async def test_unified_shows_leads_in_stages(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        lead_stages: list[PipelineStage],
        opp_stages: list[PipelineStage],
    ):
        """Unified pipeline shows leads in their pipeline stages."""
        new_stage = lead_stages[0]
        lead = Lead(
            first_name="Unified",
            last_name="Test",
            email="unified.test@example.com",
            status="new",
            score=60,
            pipeline_stage_id=new_stage.id,
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(lead)
        await db_session.commit()

        response = await client.get(
            "/api/dashboard/pipeline/unified",
            headers=auth_headers,
        )
        data = response.json()

        new_stage_data = next(
            s for s in data["lead_stages"] if s["stage_name"] == "New"
        )
        assert new_stage_data["count"] == 1
        assert new_stage_data["items"][0]["name"] == "Unified Test"
        assert new_stage_data["items"][0]["entity_type"] == "lead"

    @pytest.mark.asyncio
    async def test_unified_shows_opportunities_with_total_value(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        lead_stages: list[PipelineStage],
        opp_stages: list[PipelineStage],
    ):
        """Unified pipeline shows opportunities with total_value."""
        qual_stage = opp_stages[0]
        opp = Opportunity(
            name="Test Deal",
            pipeline_stage_id=qual_stage.id,
            amount=50000.0,
            currency="USD",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(opp)
        await db_session.commit()

        response = await client.get(
            "/api/dashboard/pipeline/unified",
            headers=auth_headers,
        )
        data = response.json()

        qual_data = next(
            s for s in data["opportunity_stages"] if s["stage_name"] == "Qualification"
        )
        assert qual_data["count"] == 1
        assert qual_data["total_value"] == 50000.0
        assert qual_data["items"][0]["name"] == "Test Deal"
        assert qual_data["items"][0]["entity_type"] == "opportunity"

    @pytest.mark.asyncio
    async def test_unified_empty_when_no_stages(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_user: User,
    ):
        """Unified pipeline returns empty lists when no stages exist."""
        response = await client.get(
            "/api/dashboard/pipeline/unified",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["lead_stages"] == []
        assert data["opportunity_stages"] == []
