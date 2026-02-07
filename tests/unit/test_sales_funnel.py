"""
Unit tests for sales funnel dashboard endpoint.

Tests for the funnel report that shows leads by status, conversion rates, and avg time.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.leads.models import Lead, LeadSource


@pytest.fixture
async def funnel_leads(db_session: AsyncSession, test_user: User, test_lead_source: LeadSource):
    """Create leads in various stages for funnel testing."""
    leads = []
    statuses = {
        "new": 10,
        "contacted": 7,
        "qualified": 4,
        "converted": 2,
    }
    for status, count in statuses.items():
        for i in range(count):
            lead = Lead(
                first_name=f"{status.title()}{i}",
                last_name="Lead",
                email=f"{status}{i}@example.com",
                status=status,
                score=20 + i * 5,
                source_id=test_lead_source.id,
                owner_id=test_user.id,
                created_by_id=test_user.id,
            )
            db_session.add(lead)
            leads.append(lead)
    await db_session.commit()
    return leads


class TestSalesFunnel:
    """Tests for the sales funnel endpoint."""

    @pytest.mark.asyncio
    async def test_get_sales_funnel_empty(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test funnel data when no leads exist."""
        response = await client.get(
            "/api/dashboard/funnel",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "stages" in data
        assert "conversions" in data
        assert "avg_days_in_stage" in data
        # Stages should still be present with 0 counts
        assert len(data["stages"]) == 4
        for stage in data["stages"]:
            assert stage["count"] == 0

    @pytest.mark.asyncio
    async def test_get_sales_funnel_with_data(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        funnel_leads: list,
    ):
        """Test funnel data with leads in various stages."""
        response = await client.get(
            "/api/dashboard/funnel",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()

        # Check stages
        stages = {s["stage"]: s["count"] for s in data["stages"]}
        assert stages["new"] == 10
        assert stages["contacted"] == 7
        assert stages["qualified"] == 4
        assert stages["converted"] == 2

        # Check conversions exist
        assert len(data["conversions"]) == 3
        conversion_map = {c["from_stage"]: c for c in data["conversions"]}
        assert "new" in conversion_map
        assert "contacted" in conversion_map
        assert "qualified" in conversion_map

        # Check conversion rates
        # new -> contacted: 7/10 = 70%
        assert conversion_map["new"]["rate"] == 70.0
        # contacted -> qualified: 4/7 ~= 57.1%
        assert conversion_map["contacted"]["rate"] == pytest.approx(57.1, abs=0.1)
        # qualified -> converted: 2/4 = 50%
        assert conversion_map["qualified"]["rate"] == 50.0

    @pytest.mark.asyncio
    async def test_get_sales_funnel_stage_order(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        funnel_leads: list,
    ):
        """Test that funnel stages are in correct order."""
        response = await client.get(
            "/api/dashboard/funnel",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()

        stage_order = [s["stage"] for s in data["stages"]]
        assert stage_order == ["new", "contacted", "qualified", "converted"]

    @pytest.mark.asyncio
    async def test_get_sales_funnel_has_avg_days(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        funnel_leads: list,
    ):
        """Test that avg_days_in_stage is populated."""
        response = await client.get(
            "/api/dashboard/funnel",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()

        avg_days = data["avg_days_in_stage"]
        assert "new" in avg_days
        assert "contacted" in avg_days
        assert "qualified" in avg_days
        assert "converted" in avg_days

    @pytest.mark.asyncio
    async def test_get_sales_funnel_colors(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        funnel_leads: list,
    ):
        """Test that funnel stages have color information."""
        response = await client.get(
            "/api/dashboard/funnel",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()

        for stage in data["stages"]:
            assert stage.get("color") is not None


class TestSalesFunnelUnauthorized:
    """Tests for unauthorized access to sales funnel."""

    @pytest.mark.asyncio
    async def test_get_funnel_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        response = await client.get("/api/dashboard/funnel")
        assert response.status_code == 401
