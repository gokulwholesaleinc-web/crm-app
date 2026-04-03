"""
Unit tests for dashboard date range filtering.

Tests that KPI and chart endpoints correctly filter data by date_from and date_to parameters.
"""

import pytest
from datetime import date, datetime, timedelta
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.leads.models import Lead, LeadSource
from src.opportunities.models import Opportunity, PipelineStage
from src.activities.models import Activity
from src.contacts.models import Contact
from src.companies.models import Company
from src.dashboard.router import _dashboard_cache
from src.auth.dependencies import _user_cache


@pytest.fixture(autouse=True)
def clear_caches():
    """Clear dashboard and auth caches before each test to prevent stale data."""
    _dashboard_cache.clear()
    _user_cache.clear()
    yield
    _dashboard_cache.clear()
    _user_cache.clear()


@pytest.fixture
async def date_range_data(
    db_session: AsyncSession,
    test_user: User,
    test_pipeline_stage: PipelineStage,
    test_lead_source: LeadSource,
):
    """Create test data with specific dates for date range testing."""
    from sqlalchemy import update

    today = date.today()
    old_date = datetime(2024, 1, 15, 12, 0, 0)

    # Old lead (should be excluded when filtering recent dates)
    old_lead = Lead(
        first_name="Old",
        last_name="Lead",
        email="old@test.com",
        status="new",
        score=30,
        source_id=test_lead_source.id,
        owner_id=test_user.id,
        created_by_id=test_user.id,
    )
    db_session.add(old_lead)
    await db_session.flush()
    old_lead_id = old_lead.id

    # Recent leads (should be included when filtering recent dates)
    recent_lead1 = Lead(
        first_name="Recent",
        last_name="Lead1",
        email="recent1@test.com",
        status="new",
        score=50,
        source_id=test_lead_source.id,
        owner_id=test_user.id,
        created_by_id=test_user.id,
    )
    db_session.add(recent_lead1)

    recent_lead2 = Lead(
        first_name="Recent",
        last_name="Lead2",
        email="recent2@test.com",
        status="contacted",
        score=60,
        source_id=test_lead_source.id,
        owner_id=test_user.id,
        created_by_id=test_user.id,
    )
    db_session.add(recent_lead2)

    # Old contact
    old_contact = Contact(
        first_name="Old",
        last_name="Contact",
        email="old_contact@test.com",
        status="active",
        owner_id=test_user.id,
        created_by_id=test_user.id,
    )
    db_session.add(old_contact)
    await db_session.flush()
    old_contact_id = old_contact.id

    # Recent contact
    recent_contact = Contact(
        first_name="Recent",
        last_name="Contact",
        email="recent_contact@test.com",
        status="active",
        owner_id=test_user.id,
        created_by_id=test_user.id,
    )
    db_session.add(recent_contact)

    # Old opportunity
    old_opp = Opportunity(
        name="Old Deal",
        pipeline_stage_id=test_pipeline_stage.id,
        amount=10000.0,
        owner_id=test_user.id,
        created_by_id=test_user.id,
    )
    db_session.add(old_opp)
    await db_session.flush()
    old_opp_id = old_opp.id

    # Recent opportunity
    recent_opp = Opportunity(
        name="Recent Deal",
        pipeline_stage_id=test_pipeline_stage.id,
        amount=50000.0,
        owner_id=test_user.id,
        created_by_id=test_user.id,
    )
    db_session.add(recent_opp)
    await db_session.flush()

    # Set old dates using Core update to avoid detached instance issues
    await db_session.execute(
        update(Lead).where(Lead.id == old_lead_id).values(created_at=old_date)
    )
    await db_session.execute(
        update(Contact).where(Contact.id == old_contact_id).values(created_at=old_date)
    )
    await db_session.execute(
        update(Opportunity).where(Opportunity.id == old_opp_id).values(created_at=old_date)
    )

    await db_session.commit()

    return {
        "old_date": old_date.date(),
        "recent_date": today,
    }


class TestKPIsWithDateRange:
    """Tests for KPI endpoints with date range filtering."""

    @pytest.mark.asyncio
    async def test_kpis_without_date_params_returns_all(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        date_range_data: dict,
    ):
        """KPIs without date params should return all-time data."""
        response = await client.get("/api/dashboard/kpis", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0

        # Find total_leads KPI - should include both old and recent
        leads_kpi = next((k for k in data if k["id"] == "total_leads"), None)
        assert leads_kpi is not None
        # 3 leads total: 1 old + 2 recent
        assert leads_kpi["value"] == 3

    @pytest.mark.asyncio
    async def test_kpis_with_date_from_filters_old_data(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        date_range_data: dict,
    ):
        """KPIs with date_from should exclude data before that date."""
        today = date.today()
        date_from = today.isoformat()

        response = await client.get(
            "/api/dashboard/kpis",
            headers=auth_headers,
            params={"date_from": date_from},
        )

        assert response.status_code == 200
        data = response.json()

        # Find total_leads KPI - should only include recent leads
        leads_kpi = next((k for k in data if k["id"] == "total_leads"), None)
        assert leads_kpi is not None
        # Only 2 recent leads (created today)
        assert leads_kpi["value"] == 2

    @pytest.mark.asyncio
    async def test_kpis_with_date_to_filters_recent_data(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        date_range_data: dict,
    ):
        """KPIs with date_to in the past should only include old data."""
        date_to = "2024-02-01"

        response = await client.get(
            "/api/dashboard/kpis",
            headers=auth_headers,
            params={"date_to": date_to},
        )

        assert response.status_code == 200
        data = response.json()

        # Find total_leads KPI - should only include old leads
        leads_kpi = next((k for k in data if k["id"] == "total_leads"), None)
        assert leads_kpi is not None
        # Only 1 old lead
        assert leads_kpi["value"] == 1

    @pytest.mark.asyncio
    async def test_kpis_with_full_date_range(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        date_range_data: dict,
    ):
        """KPIs with both date_from and date_to should filter to the range."""
        response = await client.get(
            "/api/dashboard/kpis",
            headers=auth_headers,
            params={
                "date_from": "2024-01-01",
                "date_to": "2024-12-31",
            },
        )

        assert response.status_code == 200
        data = response.json()

        # Find total_leads KPI
        leads_kpi = next((k for k in data if k["id"] == "total_leads"), None)
        assert leads_kpi is not None
        # Only the old lead (created 2024-01-15)
        assert leads_kpi["value"] == 1

    @pytest.mark.asyncio
    async def test_kpis_contacts_filtered_by_date(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        date_range_data: dict,
    ):
        """Total contacts KPI should be filtered by date range."""
        today = date.today()
        response = await client.get(
            "/api/dashboard/kpis",
            headers=auth_headers,
            params={"date_from": today.isoformat()},
        )

        assert response.status_code == 200
        data = response.json()

        contacts_kpi = next((k for k in data if k["id"] == "total_contacts"), None)
        assert contacts_kpi is not None
        # Only 1 recent contact
        assert contacts_kpi["value"] == 1

    @pytest.mark.asyncio
    async def test_kpis_opportunities_filtered_by_date(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        date_range_data: dict,
    ):
        """Open opportunities KPI should be filtered by date range."""
        today = date.today()
        response = await client.get(
            "/api/dashboard/kpis",
            headers=auth_headers,
            params={"date_from": today.isoformat()},
        )

        assert response.status_code == 200
        data = response.json()

        opps_kpi = next((k for k in data if k["id"] == "open_opportunities"), None)
        assert opps_kpi is not None
        # Only 1 recent opportunity
        assert opps_kpi["value"] == 1


class TestSalesKpisWithDateRange:
    """Tests for sales KPIs endpoint with date range filtering."""

    @pytest.mark.asyncio
    async def test_sales_kpis_accepts_date_params(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Sales KPIs endpoint should accept date_from and date_to params."""
        today = date.today()
        response = await client.get(
            "/api/dashboard/sales-kpis",
            headers=auth_headers,
            params={
                "date_from": today.isoformat(),
                "date_to": today.isoformat(),
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "quotes_sent" in data
        assert "proposals_sent" in data
        assert "payments_collected_total" in data

    @pytest.mark.asyncio
    async def test_sales_kpis_without_date_params(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Sales KPIs should work without date params (all-time)."""
        response = await client.get(
            "/api/dashboard/sales-kpis",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "quotes_sent" in data


class TestChartEndpointsWithDateRange:
    """Tests for chart endpoints with date range filtering."""

    @pytest.mark.asyncio
    async def test_pipeline_funnel_accepts_date_range(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        date_range_data: dict,
    ):
        """Pipeline funnel chart should accept date range params."""
        today = date.today()
        response = await client.get(
            "/api/dashboard/charts/pipeline-funnel",
            headers=auth_headers,
            params={"date_from": today.isoformat()},
        )

        assert response.status_code == 200
        data = response.json()
        assert "type" in data
        assert "data" in data

    @pytest.mark.asyncio
    async def test_leads_by_status_accepts_date_range(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        date_range_data: dict,
    ):
        """Leads by status chart should filter by date range."""
        today = date.today()
        response = await client.get(
            "/api/dashboard/charts/leads-by-status",
            headers=auth_headers,
            params={"date_from": today.isoformat()},
        )

        assert response.status_code == 200
        data = response.json()
        assert "data" in data

        # Only recent leads should be counted
        total_count = sum(d["value"] for d in data["data"])
        assert total_count == 2  # 2 recent leads

    @pytest.mark.asyncio
    async def test_leads_by_source_accepts_date_range(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        date_range_data: dict,
    ):
        """Leads by source chart should accept date range params."""
        response = await client.get(
            "/api/dashboard/charts/leads-by-source",
            headers=auth_headers,
            params={"date_from": date.today().isoformat()},
        )

        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    @pytest.mark.asyncio
    async def test_activities_chart_accepts_date_range(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Activities chart should accept date range params."""
        response = await client.get(
            "/api/dashboard/charts/activities",
            headers=auth_headers,
            params={
                "date_from": date.today().isoformat(),
                "date_to": date.today().isoformat(),
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    @pytest.mark.asyncio
    async def test_conversion_rates_accepts_date_range(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Conversion rates chart should accept date range params."""
        response = await client.get(
            "/api/dashboard/charts/conversion-rates",
            headers=auth_headers,
            params={"date_from": "2024-01-01", "date_to": "2024-12-31"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    @pytest.mark.asyncio
    async def test_funnel_accepts_date_range(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        date_range_data: dict,
    ):
        """Sales funnel endpoint should accept date range params."""
        response = await client.get(
            "/api/dashboard/funnel",
            headers=auth_headers,
            params={"date_from": date.today().isoformat()},
        )

        assert response.status_code == 200
        data = response.json()
        assert "stages" in data
        assert "conversions" in data


class TestDateRangeCaching:
    """Tests that different date ranges produce separate cache entries."""

    @pytest.mark.asyncio
    async def test_different_date_ranges_not_cached_together(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        date_range_data: dict,
    ):
        """Two requests with different date ranges should return different results."""
        # First request: all time (no date filter)
        response_all = await client.get(
            "/api/dashboard/kpis",
            headers=auth_headers,
        )
        assert response_all.status_code == 200
        all_data = response_all.json()

        # Second request: only today
        response_today = await client.get(
            "/api/dashboard/kpis",
            headers=auth_headers,
            params={"date_from": date.today().isoformat()},
        )
        assert response_today.status_code == 200
        today_data = response_today.json()

        # They should have different total_leads values
        all_leads = next((k for k in all_data if k["id"] == "total_leads"), None)
        today_leads = next((k for k in today_data if k["id"] == "total_leads"), None)
        assert all_leads is not None
        assert today_leads is not None
        assert all_leads["value"] > today_leads["value"]
