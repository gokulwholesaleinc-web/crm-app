"""
Unit tests for dashboard endpoints.

Tests for number cards (KPIs) and chart data endpoints.
"""

import pytest
from datetime import date, timedelta
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.leads.models import Lead, LeadSource
from src.opportunities.models import Opportunity, PipelineStage
from src.activities.models import Activity
from src.contacts.models import Contact
from src.companies.models import Company


@pytest.mark.skip(reason="date_trunc requires PostgreSQL; SQLite test DB unsupported")
class TestDashboardFull:
    """Tests for full dashboard endpoint."""

    @pytest.mark.asyncio
    async def test_get_dashboard_empty(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test getting dashboard when no data exists."""
        response = await client.get("/api/dashboard", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert "number_cards" in data
        assert "charts" in data
        assert isinstance(data["number_cards"], list)
        assert isinstance(data["charts"], list)

    @pytest.mark.asyncio
    async def test_get_dashboard_with_data(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_lead: Lead,
        test_opportunity: Opportunity,
        test_activity: Activity,
    ):
        """Test getting dashboard with existing data."""
        response = await client.get("/api/dashboard", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()

        # Check number cards structure
        assert len(data["number_cards"]) > 0
        for card in data["number_cards"]:
            assert "id" in card
            assert "label" in card
            assert "value" in card
            assert "color" in card

        # Check charts structure
        assert len(data["charts"]) > 0
        for chart in data["charts"]:
            assert "type" in chart
            assert "title" in chart
            assert "data" in chart
            assert isinstance(chart["data"], list)


class TestKPIs:
    """Tests for KPI number cards endpoint."""

    @pytest.mark.asyncio
    async def test_get_kpis_empty(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test getting KPIs when no data exists."""
        response = await client.get("/api/dashboard/kpis", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_get_kpis_with_data(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_lead: Lead,
        test_opportunity: Opportunity,
        test_contact: Contact,
    ):
        """Test getting KPIs with existing data."""
        response = await client.get("/api/dashboard/kpis", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert len(data) > 0

        # Check structure of each KPI card
        for kpi in data:
            assert "id" in kpi
            assert "label" in kpi
            assert "value" in kpi

    @pytest.mark.asyncio
    async def test_kpis_include_common_metrics(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_pipeline_stage: PipelineStage,
    ):
        """Test KPIs include common business metrics."""
        # Create some data to ensure metrics are computed
        for i in range(5):
            lead = Lead(
                first_name=f"Lead{i}",
                last_name="Test",
                email=f"lead{i}@test.com",
                status="new",
                owner_id=test_user.id,
                created_by_id=test_user.id,
            )
            db_session.add(lead)

        for i in range(3):
            opp = Opportunity(
                name=f"Deal {i}",
                pipeline_stage_id=test_pipeline_stage.id,
                amount=50000.0,
                owner_id=test_user.id,
                created_by_id=test_user.id,
            )
            db_session.add(opp)

        await db_session.commit()

        response = await client.get("/api/dashboard/kpis", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()

        # Should have some KPI cards
        assert len(data) > 0
        kpi_ids = [k["id"] for k in data]
        # Common KPIs should be present (at least some)
        assert len(kpi_ids) > 0


class TestPipelineFunnelChart:
    """Tests for pipeline funnel chart endpoint."""

    @pytest.mark.asyncio
    async def test_get_pipeline_funnel_empty(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test getting pipeline funnel with no data."""
        response = await client.get(
            "/api/dashboard/charts/pipeline-funnel",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["type"] in ["funnel", "bar"]
        assert "title" in data
        assert "data" in data
        assert isinstance(data["data"], list)

    @pytest.mark.asyncio
    async def test_get_pipeline_funnel_with_data(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_opportunity: Opportunity,
        test_pipeline_stage: PipelineStage,
    ):
        """Test getting pipeline funnel with opportunity data."""
        response = await client.get(
            "/api/dashboard/charts/pipeline-funnel",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) > 0

        # Each data point should have label and value
        for point in data["data"]:
            assert "label" in point
            assert "value" in point


class TestLeadsByStatusChart:
    """Tests for leads by status chart endpoint."""

    @pytest.mark.asyncio
    async def test_get_leads_by_status_empty(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test getting leads by status with no data."""
        response = await client.get(
            "/api/dashboard/charts/leads-by-status",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "type" in data
        assert "title" in data
        assert "data" in data

    @pytest.mark.asyncio
    async def test_get_leads_by_status_with_data(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Test getting leads by status with lead data."""
        # Create leads with different statuses
        for status in ["new", "contacted", "qualified"]:
            lead = Lead(
                first_name="Status",
                last_name=status,
                email=f"{status}@test.com",
                status=status,
                owner_id=test_user.id,
                created_by_id=test_user.id,
            )
            db_session.add(lead)
        await db_session.commit()

        response = await client.get(
            "/api/dashboard/charts/leads-by-status",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) > 0


class TestLeadsBySourceChart:
    """Tests for leads by source chart endpoint."""

    @pytest.mark.asyncio
    async def test_get_leads_by_source_empty(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test getting leads by source with no data."""
        response = await client.get(
            "/api/dashboard/charts/leads-by-source",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "type" in data
        assert "title" in data
        assert "data" in data

    @pytest.mark.asyncio
    async def test_get_leads_by_source_with_data(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_lead: Lead,
        test_lead_source: LeadSource,
    ):
        """Test getting leads by source with lead data."""
        response = await client.get(
            "/api/dashboard/charts/leads-by-source",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["data"], list)


@pytest.mark.skip(reason="date_trunc requires PostgreSQL; SQLite test DB unsupported")
class TestRevenueTrendChart:
    """Tests for revenue trend chart endpoint."""

    @pytest.mark.asyncio
    async def test_get_revenue_trend_empty(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test getting revenue trend with no data."""
        response = await client.get(
            "/api/dashboard/charts/revenue-trend",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["type"] in ["line", "area", "bar"]
        assert "title" in data
        assert "data" in data

    @pytest.mark.asyncio
    async def test_get_revenue_trend_with_custom_months(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test getting revenue trend with custom month parameter."""
        response = await client.get(
            "/api/dashboard/charts/revenue-trend",
            headers=auth_headers,
            params={"months": 3},
        )

        assert response.status_code == 200
        data = response.json()
        # Should have data points for 3 months
        assert len(data["data"]) <= 3

    @pytest.mark.asyncio
    async def test_get_revenue_trend_with_data(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_won_stage: PipelineStage,
    ):
        """Test getting revenue trend with won opportunities."""
        # Create a won opportunity
        opp = Opportunity(
            name="Won Deal",
            pipeline_stage_id=test_won_stage.id,
            amount=100000.0,
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(opp)
        await db_session.commit()

        response = await client.get(
            "/api/dashboard/charts/revenue-trend",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["data"], list)


class TestActivitiesChart:
    """Tests for activities by type chart endpoint."""

    @pytest.mark.asyncio
    async def test_get_activities_chart_empty(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test getting activities chart with no data."""
        response = await client.get(
            "/api/dashboard/charts/activities",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "type" in data
        assert "title" in data
        assert "data" in data

    @pytest.mark.asyncio
    async def test_get_activities_chart_with_custom_days(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test getting activities chart with custom days parameter."""
        response = await client.get(
            "/api/dashboard/charts/activities",
            headers=auth_headers,
            params={"days": 7},
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["data"], list)

    @pytest.mark.asyncio
    async def test_get_activities_chart_with_data(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_activity: Activity,
    ):
        """Test getting activities chart with activity data."""
        response = await client.get(
            "/api/dashboard/charts/activities",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["data"], list)


@pytest.mark.skip(reason="date_trunc requires PostgreSQL; SQLite test DB unsupported")
class TestNewLeadsTrendChart:
    """Tests for new leads trend chart endpoint."""

    @pytest.mark.asyncio
    async def test_get_new_leads_trend_empty(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test getting new leads trend with no data."""
        response = await client.get(
            "/api/dashboard/charts/new-leads-trend",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "type" in data
        assert "title" in data
        assert "data" in data

    @pytest.mark.asyncio
    async def test_get_new_leads_trend_with_custom_weeks(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test getting new leads trend with custom weeks parameter."""
        response = await client.get(
            "/api/dashboard/charts/new-leads-trend",
            headers=auth_headers,
            params={"weeks": 4},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) <= 4

    @pytest.mark.asyncio
    async def test_get_new_leads_trend_with_data(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_lead: Lead,
    ):
        """Test getting new leads trend with lead data."""
        response = await client.get(
            "/api/dashboard/charts/new-leads-trend",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["data"], list)


class TestConversionRatesChart:
    """Tests for conversion rates chart endpoint."""

    @pytest.mark.asyncio
    async def test_get_conversion_rates_empty(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test getting conversion rates with no data."""
        response = await client.get(
            "/api/dashboard/charts/conversion-rates",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "type" in data
        assert "title" in data
        assert "data" in data

    @pytest.mark.asyncio
    async def test_get_conversion_rates_with_data(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_pipeline_stage: PipelineStage,
        test_won_stage: PipelineStage,
    ):
        """Test getting conversion rates with opportunity data."""
        # Create some won and lost opportunities
        for i in range(3):
            opp = Opportunity(
                name=f"Deal {i}",
                pipeline_stage_id=test_won_stage.id,
                amount=50000.0,
                owner_id=test_user.id,
                created_by_id=test_user.id,
            )
            db_session.add(opp)
        await db_session.commit()

        response = await client.get(
            "/api/dashboard/charts/conversion-rates",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["data"], list)


class TestDashboardUnauthorized:
    """Tests for unauthorized access to dashboard endpoints."""

    @pytest.mark.asyncio
    async def test_get_dashboard_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test getting dashboard without auth fails."""
        response = await client.get("/api/dashboard")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_kpis_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test getting KPIs without auth fails."""
        response = await client.get("/api/dashboard/kpis")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_pipeline_funnel_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test getting pipeline funnel without auth fails."""
        response = await client.get("/api/dashboard/charts/pipeline-funnel")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_revenue_trend_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test getting revenue trend without auth fails."""
        response = await client.get("/api/dashboard/charts/revenue-trend")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_leads_by_source_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test getting leads by source without auth fails."""
        response = await client.get("/api/dashboard/charts/leads-by-source")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_activities_chart_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test getting activities chart without auth fails."""
        response = await client.get("/api/dashboard/charts/activities")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_new_leads_trend_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test getting new leads trend without auth fails."""
        response = await client.get("/api/dashboard/charts/new-leads-trend")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_conversion_rates_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test getting conversion rates without auth fails."""
        response = await client.get("/api/dashboard/charts/conversion-rates")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_sales_funnel_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test getting sales funnel without auth fails."""
        response = await client.get("/api/dashboard/funnel")
        assert response.status_code == 401


class TestSalesFunnel:
    """Tests for sales funnel endpoint."""

    @pytest.mark.asyncio
    async def test_get_sales_funnel_empty(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test getting sales funnel when no data exists."""
        response = await client.get("/api/dashboard/funnel", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert "stages" in data
        assert "conversions" in data
        assert "avg_days_in_stage" in data
        assert isinstance(data["stages"], list)
        assert isinstance(data["conversions"], list)
        assert isinstance(data["avg_days_in_stage"], dict)

    @pytest.mark.asyncio
    async def test_get_sales_funnel_with_data(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Test getting sales funnel with lead data across stages."""
        # Create leads with different statuses to populate the funnel
        for status in ["new", "contacted", "qualified", "converted"]:
            lead = Lead(
                first_name="Funnel",
                last_name=status,
                email=f"funnel-{status}@test.com",
                status=status,
                owner_id=test_user.id,
                created_by_id=test_user.id,
            )
            db_session.add(lead)
        await db_session.commit()

        response = await client.get("/api/dashboard/funnel", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert "stages" in data
        assert isinstance(data["stages"], list)
        # Each stage should have stage name and count
        for stage in data["stages"]:
            assert "stage" in stage
            assert "count" in stage


# ---------------------------------------------------------------------------
# Admin user-switcher (PR B)
# ---------------------------------------------------------------------------

class TestDashboardAdminUserSwitcher:
    """Verify the ``owner_id`` query param on /api/dashboard/kpis +
    /api/dashboard/sales-kpis is honored only for admin/manager.

    Sales reps passing someone else's owner_id are silently coerced to
    themselves by ``effective_owner_id`` — that's the public contract.
    """

    @pytest.mark.asyncio
    async def test_sales_rep_owner_id_is_coerced_to_self(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_pipeline_stage: PipelineStage,
    ):
        """Sales rep passing a peer's id sees only their own KPIs.

        Construct two users with different opportunity counts. Sales-rep
        token belongs to user A. Pass owner_id=B's id. KPIs returned
        must reflect A's data (because effective_owner_id silently
        coerces back).
        """
        from src.auth.security import get_password_hash

        peer = User(
            email="peer-rep@example.com",
            hashed_password=get_password_hash("peer123"),
            full_name="Peer Rep",
            is_active=True,
            is_superuser=False,
        )
        db_session.add(peer)
        await db_session.commit()
        await db_session.refresh(peer)

        # 5 opps for caller, 1 for peer.
        for i in range(5):
            db_session.add(
                Opportunity(
                    name=f"My Deal {i}",
                    pipeline_stage_id=test_pipeline_stage.id,
                    amount=100.0,
                    owner_id=test_user.id,
                    created_by_id=test_user.id,
                )
            )
        db_session.add(
            Opportunity(
                name="Peer Deal",
                pipeline_stage_id=test_pipeline_stage.id,
                amount=999.0,
                owner_id=peer.id,
                created_by_id=peer.id,
            )
        )
        await db_session.commit()

        response = await client.get(
            f"/api/dashboard/kpis?owner_id={peer.id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        kpis = {k["id"]: k for k in response.json()}
        # open_opportunities should reflect 5 (caller's), not 1 (peer's).
        opps = kpis.get("open_opportunities")
        assert opps is not None
        assert opps["value"] == 5

    @pytest.mark.asyncio
    async def test_admin_can_scope_to_another_user(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict,
        test_user: User,
        test_pipeline_stage: PipelineStage,
    ):
        """Admin passing owner_id=test_user.id sees test_user's KPIs."""
        for i in range(3):
            db_session.add(
                Opportunity(
                    name=f"User Deal {i}",
                    pipeline_stage_id=test_pipeline_stage.id,
                    amount=200.0,
                    owner_id=test_user.id,
                    created_by_id=test_user.id,
                )
            )
        await db_session.commit()

        response = await client.get(
            f"/api/dashboard/kpis?owner_id={test_user.id}",
            headers=admin_auth_headers,
        )
        assert response.status_code == 200
        kpis = {k["id"]: k for k in response.json()}
        opps = kpis.get("open_opportunities")
        assert opps is not None
        assert opps["value"] == 3

    @pytest.mark.asyncio
    async def test_admin_no_owner_id_returns_tenant_wide(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict,
        test_user: User,
        test_pipeline_stage: PipelineStage,
    ):
        """Admin without owner_id sees the rollup across all users.

        Two distinct owners, 2 + 4 = 6 opps total. Admin omits owner_id.
        ``effective_owner_id`` returns None (admin can_see_all → pass
        through requested_owner_id, which was None) → generators see
        ``user_id=None`` → no owner filter.
        """
        from src.auth.security import get_password_hash

        peer = User(
            email="another-rep@example.com",
            hashed_password=get_password_hash("rep123"),
            full_name="Another Rep",
            is_active=True,
            is_superuser=False,
        )
        db_session.add(peer)
        await db_session.commit()
        await db_session.refresh(peer)

        for i in range(2):
            db_session.add(
                Opportunity(
                    name=f"A {i}",
                    pipeline_stage_id=test_pipeline_stage.id,
                    amount=10.0,
                    owner_id=test_user.id,
                    created_by_id=test_user.id,
                )
            )
        for i in range(4):
            db_session.add(
                Opportunity(
                    name=f"B {i}",
                    pipeline_stage_id=test_pipeline_stage.id,
                    amount=10.0,
                    owner_id=peer.id,
                    created_by_id=peer.id,
                )
            )
        await db_session.commit()

        response = await client.get("/api/dashboard/kpis", headers=admin_auth_headers)
        assert response.status_code == 200
        kpis = {k["id"]: k for k in response.json()}
        opps = kpis.get("open_opportunities")
        assert opps is not None
        # Tenant-wide rollup includes the 6 we just inserted plus any
        # admin-fixture-owned opps from upstream conftest. Asserting the
        # lower bound keeps this test stable if the admin fixture later
        # seeds its own sample data.
        assert opps["value"] >= 6

    @pytest.mark.asyncio
    async def test_sales_rep_own_id_passes_through(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_pipeline_stage: PipelineStage,
    ):
        """Sales rep passing their OWN id as ``owner_id`` is a no-op.

        Equivalent to omitting the param. Confirms the coercion in
        ``effective_owner_id`` is symmetric — passing self.id doesn't
        accidentally widen or narrow the scope.
        """
        for i in range(2):
            db_session.add(
                Opportunity(
                    name=f"Self Deal {i}",
                    pipeline_stage_id=test_pipeline_stage.id,
                    amount=50.0,
                    owner_id=test_user.id,
                    created_by_id=test_user.id,
                )
            )
        await db_session.commit()

        response = await client.get(
            f"/api/dashboard/kpis?owner_id={test_user.id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        kpis = {k["id"]: k for k in response.json()}
        opps = kpis.get("open_opportunities")
        assert opps is not None
        assert opps["value"] == 2

    @pytest.mark.asyncio
    async def test_sales_kpis_admin_owner_id_pass_through(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict,
        test_user: User,
    ):
        """Admin scoping /sales-kpis to a peer reflects that peer's
        proposals/quotes/payments, not the admin's."""
        from src.proposals.models import Proposal

        for i in range(3):
            db_session.add(
                Proposal(
                    proposal_number=f"PR-DASH-B-{i}",
                    title=f"Dash B Proposal {i}",
                    status="sent",
                    owner_id=test_user.id,
                    created_by_id=test_user.id,
                )
            )
        await db_session.commit()

        response = await client.get(
            f"/api/dashboard/sales-kpis?owner_id={test_user.id}",
            headers=admin_auth_headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["proposals_sent"] == 3
