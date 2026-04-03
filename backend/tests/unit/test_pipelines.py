"""
Unit tests for multiple pipelines CRUD endpoints.

Tests for pipeline listing, creation, retrieval, updating, and deletion.

NOTE: These tests require a Pipeline model that does not yet exist.
The multi-pipeline feature is not yet implemented. All tests are skipped.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.auth.models import User
from src.opportunities.models import PipelineStage, Opportunity

# Pipeline model does not exist yet — skip the entire module
pytestmark = pytest.mark.skip(reason="Pipeline model not implemented yet")

# Placeholder so type references don't break at module scope
Pipeline = None


class TestPipelineList:
    """Tests for listing pipelines."""

    @pytest.mark.asyncio
    async def test_list_pipelines_empty(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test listing pipelines when none exist."""
        response = await client.get("/api/pipelines", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert isinstance(data["items"], list)

    @pytest.mark.asyncio
    async def test_list_pipelines_with_data(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_pipeline: Pipeline,
    ):
        """Test listing pipelines returns existing pipeline."""
        response = await client.get("/api/pipelines", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        assert any(p["id"] == test_pipeline.id for p in data["items"])

    @pytest.mark.asyncio
    async def test_list_pipelines_unauthorized(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Test listing pipelines without auth fails."""
        response = await client.get("/api/pipelines")
        assert response.status_code == 401


class TestPipelineCreate:
    """Tests for creating pipelines."""

    @pytest.mark.asyncio
    async def test_create_pipeline_basic(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test creating a pipeline with basic info."""
        response = await client.post(
            "/api/pipelines",
            headers=auth_headers,
            json={
                "name": "Enterprise Pipeline",
                "description": "For enterprise deals",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Enterprise Pipeline"
        assert data["description"] == "For enterprise deals"
        assert "id" in data

    @pytest.mark.asyncio
    async def test_create_pipeline_with_stages(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test creating a pipeline with initial stages."""
        response = await client.post(
            "/api/pipelines",
            headers=auth_headers,
            json={
                "name": "Pipeline With Stages",
                "stages": [
                    {"name": "Lead", "order": 0, "probability": 10, "color": "#3b82f6"},
                    {"name": "Qualified", "order": 1, "probability": 30, "color": "#f59e0b"},
                    {"name": "Proposal", "order": 2, "probability": 60, "color": "#8b5cf6"},
                    {"name": "Won", "order": 3, "probability": 100, "is_won": True, "color": "#22c55e"},
                ],
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Pipeline With Stages"
        assert len(data["stages"]) == 4
        assert data["stages"][0]["name"] == "Lead"

    @pytest.mark.asyncio
    async def test_create_pipeline_as_default(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test creating a pipeline and setting it as default."""
        response = await client.post(
            "/api/pipelines",
            headers=auth_headers,
            json={
                "name": "New Default Pipeline",
                "is_default": True,
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["is_default"] is True

    @pytest.mark.asyncio
    async def test_create_pipeline_missing_name(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test creating a pipeline without name fails."""
        response = await client.post(
            "/api/pipelines",
            headers=auth_headers,
            json={"description": "No name pipeline"},
        )
        assert response.status_code == 422


class TestPipelineGetById:
    """Tests for getting a pipeline by ID."""

    @pytest.mark.asyncio
    async def test_get_pipeline_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_pipeline: Pipeline,
    ):
        """Test getting a pipeline by ID."""
        response = await client.get(
            f"/api/pipelines/{test_pipeline.id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == test_pipeline.id
        assert data["name"] == test_pipeline.name
        assert "stages" in data

    @pytest.mark.asyncio
    async def test_get_pipeline_not_found(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test getting non-existent pipeline returns 404."""
        response = await client.get(
            "/api/pipelines/99999",
            headers=auth_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_pipeline_includes_deal_counts(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Test that pipeline response includes deal counts per stage."""
        # Create pipeline with a stage
        pipeline = Pipeline(name="Deal Count Test", created_by_id=test_user.id)
        db_session.add(pipeline)
        await db_session.flush()

        stage = PipelineStage(
            name="Active Stage",
            order=0,
            probability=50,
            pipeline_id=pipeline.id,
        )
        db_session.add(stage)
        await db_session.flush()

        # Create opportunities in that stage
        for i in range(3):
            opp = Opportunity(
                name=f"Deal {i}",
                pipeline_stage_id=stage.id,
                pipeline_id=pipeline.id,
                amount=10000,
                owner_id=test_user.id,
                created_by_id=test_user.id,
            )
            db_session.add(opp)
        await db_session.commit()

        response = await client.get(
            f"/api/pipelines/{pipeline.id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["stages"]) == 1
        assert data["stages"][0]["deal_count"] == 3


class TestPipelineUpdate:
    """Tests for updating pipelines."""

    @pytest.mark.asyncio
    async def test_update_pipeline_name(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_pipeline: Pipeline,
    ):
        """Test updating a pipeline's name."""
        response = await client.patch(
            f"/api/pipelines/{test_pipeline.id}",
            headers=auth_headers,
            json={"name": "Updated Pipeline Name"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Pipeline Name"

    @pytest.mark.asyncio
    async def test_update_pipeline_not_found(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test updating non-existent pipeline."""
        response = await client.patch(
            "/api/pipelines/99999",
            headers=auth_headers,
            json={"name": "Ghost"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_pipeline_set_default(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Test setting a pipeline as default unsets others."""
        # Create two pipelines
        p1 = Pipeline(name="Pipeline A", is_default=True, created_by_id=test_user.id)
        p2 = Pipeline(name="Pipeline B", is_default=False, created_by_id=test_user.id)
        db_session.add_all([p1, p2])
        await db_session.commit()
        await db_session.refresh(p1)
        await db_session.refresh(p2)

        # Set p2 as default
        response = await client.patch(
            f"/api/pipelines/{p2.id}",
            headers=auth_headers,
            json={"is_default": True},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["is_default"] is True

        # Verify p1 is no longer default
        result = await db_session.execute(
            select(Pipeline).where(Pipeline.id == p1.id)
        )
        p1_refreshed = result.scalar_one()
        assert p1_refreshed.is_default is False


class TestPipelineDelete:
    """Tests for deleting pipelines."""

    @pytest.mark.asyncio
    async def test_delete_pipeline_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Test deleting a pipeline."""
        pipeline = Pipeline(name="To Delete", created_by_id=test_user.id)
        db_session.add(pipeline)
        await db_session.commit()
        await db_session.refresh(pipeline)
        pid = pipeline.id

        response = await client.delete(
            f"/api/pipelines/{pid}",
            headers=auth_headers,
        )
        assert response.status_code == 204

        # Verify deleted
        result = await db_session.execute(
            select(Pipeline).where(Pipeline.id == pid)
        )
        assert result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_delete_default_pipeline_fails(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Test that deleting the default pipeline returns 400."""
        pipeline = Pipeline(
            name="Default Cannot Delete",
            is_default=True,
            created_by_id=test_user.id,
        )
        db_session.add(pipeline)
        await db_session.commit()
        await db_session.refresh(pipeline)

        response = await client.delete(
            f"/api/pipelines/{pipeline.id}",
            headers=auth_headers,
        )
        assert response.status_code == 400
        assert "default" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_delete_pipeline_not_found(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test deleting non-existent pipeline."""
        response = await client.delete(
            "/api/pipelines/99999",
            headers=auth_headers,
        )
        assert response.status_code == 404
