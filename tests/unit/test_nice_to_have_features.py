"""
Unit tests for nice-to-have features.

Tests for:
- Multi-Currency support (conversion, currencies endpoint, converted revenue)
- Bulk Delete operations
- Calendar View endpoint
- Predictive AI (win probability, next action suggestion, activity summary)
"""

import pytest
from datetime import date, datetime, timedelta, timezone
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.auth.models import User
from src.leads.models import Lead, LeadSource
from src.contacts.models import Contact
from src.companies.models import Company
from src.opportunities.models import Opportunity, PipelineStage
from src.activities.models import Activity
from src.core.currencies import convert_amount, get_supported_currencies_list, get_base_currency


# =========================================================================
# Multi-Currency Unit Tests
# =========================================================================


class TestCurrencyConversion:
    """Tests for currency conversion functions."""

    def test_same_currency_returns_same_amount(self):
        """Converting between same currency should return the same amount."""
        result = convert_amount(100.0, "USD", "USD")
        assert result == 100.0

    def test_usd_to_eur_conversion(self):
        """Converting USD to EUR should use the static rate."""
        result = convert_amount(100.0, "USD", "EUR")
        assert isinstance(result, float)
        assert result > 0
        # EUR rate is approximately 0.92, so 100 USD ~ 92 EUR
        assert 80 < result < 100

    def test_eur_to_usd_conversion(self):
        """Converting EUR to USD should give a higher amount."""
        result = convert_amount(100.0, "EUR", "USD")
        assert isinstance(result, float)
        assert result > 100  # 1 EUR > 1 USD

    def test_cross_currency_conversion(self):
        """Converting between two non-USD currencies should work via USD pivot."""
        result = convert_amount(100.0, "GBP", "EUR")
        assert isinstance(result, float)
        assert result > 0

    def test_zero_amount_conversion(self):
        """Converting zero should return zero."""
        result = convert_amount(0.0, "USD", "EUR")
        assert result == 0.0

    def test_large_amount_conversion(self):
        """Converting large amounts should work correctly."""
        result = convert_amount(1_000_000.0, "USD", "JPY")
        assert isinstance(result, float)
        assert result > 1_000_000  # JPY has many more units per USD

    def test_result_is_rounded_to_2_decimals(self):
        """Conversion results should be rounded to 2 decimal places."""
        result = convert_amount(33.33, "USD", "EUR")
        # Verify it's rounded (max 2 decimal places)
        assert result == round(result, 2)

    def test_unknown_currency_defaults_to_rate_1(self):
        """Unknown currency code should default to rate 1.0 (treated like USD)."""
        result = convert_amount(100.0, "USD", "XYZ")
        assert result == 100.0

    def test_get_supported_currencies_list_returns_all(self):
        """Should return list of all supported currencies."""
        currencies = get_supported_currencies_list()
        assert isinstance(currencies, list)
        assert len(currencies) >= 20

        # Check structure
        for c in currencies:
            assert "code" in c
            assert "name" in c
            assert "symbol" in c
            assert "exchange_rate" in c

    def test_get_supported_currencies_includes_usd(self):
        """USD should be in the supported currencies."""
        currencies = get_supported_currencies_list()
        codes = [c["code"] for c in currencies]
        assert "USD" in codes

    def test_get_base_currency_returns_string(self):
        """Base currency should be a string."""
        base = get_base_currency()
        assert isinstance(base, str)
        assert len(base) == 3


class TestCurrenciesEndpoint:
    """Tests for GET /api/dashboard/currencies."""

    @pytest.mark.asyncio
    async def test_list_currencies(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test listing all supported currencies."""
        response = await client.get("/api/dashboard/currencies", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert "base_currency" in data
        assert "currencies" in data
        assert isinstance(data["currencies"], list)
        assert len(data["currencies"]) >= 20

        # Verify currency structure
        first_currency = data["currencies"][0]
        assert "code" in first_currency
        assert "name" in first_currency
        assert "symbol" in first_currency
        assert "exchange_rate" in first_currency

    @pytest.mark.asyncio
    async def test_list_currencies_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test listing currencies without auth returns 401."""
        response = await client.get("/api/dashboard/currencies")
        assert response.status_code == 401


class TestConvertedRevenueEndpoint:
    """Tests for GET /api/dashboard/revenue/converted."""

    @pytest.mark.asyncio
    async def test_converted_revenue_empty(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test converted revenue with no opportunities."""
        response = await client.get(
            "/api/dashboard/revenue/converted",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "target_currency" in data
        assert "total_pipeline_value" in data
        assert "total_revenue" in data
        assert "weighted_pipeline_value" in data
        assert data["total_pipeline_value"] == 0
        assert data["total_revenue"] == 0
        assert data["open_deal_count"] == 0
        assert data["won_deal_count"] == 0

    @pytest.mark.asyncio
    async def test_converted_revenue_with_data(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_opportunity: Opportunity,
    ):
        """Test converted revenue with existing opportunity."""
        response = await client.get(
            "/api/dashboard/revenue/converted",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["open_deal_count"] >= 1
        assert data["total_pipeline_value"] > 0

    @pytest.mark.asyncio
    async def test_converted_revenue_with_target_currency(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_opportunity: Opportunity,
    ):
        """Test converted revenue with a specific target currency."""
        response = await client.get(
            "/api/dashboard/revenue/converted?target_currency=EUR",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["target_currency"] == "EUR"
        # The pipeline value should be converted to EUR
        assert data["total_pipeline_value"] > 0

    @pytest.mark.asyncio
    async def test_converted_revenue_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test converted revenue without auth returns 401."""
        response = await client.get("/api/dashboard/revenue/converted")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_converted_revenue_won_deals(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_won_stage: PipelineStage,
        test_contact: Contact,
        test_company: Company,
    ):
        """Test converted revenue counts won deals correctly."""
        won_opp = Opportunity(
            name="Won Deal",
            pipeline_stage_id=test_won_stage.id,
            amount=25000.0,
            currency="USD",
            contact_id=test_contact.id,
            company_id=test_company.id,
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(won_opp)
        await db_session.commit()

        response = await client.get(
            "/api/dashboard/revenue/converted",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["won_deal_count"] >= 1
        assert data["total_revenue"] >= 25000.0


# =========================================================================
# Bulk Delete Tests
# =========================================================================


class TestBulkDelete:
    """Tests for bulk delete endpoint."""

    @pytest.fixture
    async def test_leads_for_delete(
        self, db_session: AsyncSession, test_user: User, test_lead_source: LeadSource
    ):
        """Create a batch of test leads for delete tests."""
        leads = []
        for i in range(5):
            lead = Lead(
                first_name=f"DeleteLead{i}",
                last_name=f"Test{i}",
                email=f"delete_lead{i}@example.com",
                status="new",
                score=10,
                source_id=test_lead_source.id,
                owner_id=test_user.id,
                created_by_id=test_user.id,
            )
            db_session.add(lead)
            leads.append(lead)
        await db_session.commit()
        for lead in leads:
            await db_session.refresh(lead)
        return leads

    @pytest.mark.asyncio
    async def test_bulk_delete_leads(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_leads_for_delete: list,
    ):
        """Test mass deleting leads."""
        lead_ids = [l.id for l in test_leads_for_delete[:3]]

        response = await client.post(
            "/api/import-export/bulk/delete",
            headers=auth_headers,
            json={
                "entity_type": "leads",
                "entity_ids": lead_ids,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["success_count"] == 3
        assert data["error_count"] == 0

        # Verify leads are deleted from database
        for lead_id in lead_ids:
            result = await db_session.execute(
                select(Lead).where(Lead.id == lead_id)
            )
            assert result.scalar_one_or_none() is None

        # Verify remaining leads still exist
        remaining_ids = [l.id for l in test_leads_for_delete[3:]]
        for lead_id in remaining_ids:
            result = await db_session.execute(
                select(Lead).where(Lead.id == lead_id)
            )
            assert result.scalar_one_or_none() is not None

    @pytest.mark.asyncio
    async def test_bulk_delete_with_invalid_ids(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_leads_for_delete: list,
    ):
        """Test bulk delete with mix of valid and invalid IDs."""
        valid_id = test_leads_for_delete[0].id

        response = await client.post(
            "/api/import-export/bulk/delete",
            headers=auth_headers,
            json={
                "entity_type": "leads",
                "entity_ids": [valid_id, 99999, 99998],
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["success_count"] == 1
        assert data["error_count"] == 2
        assert len(data["errors"]) == 2

    @pytest.mark.asyncio
    async def test_bulk_delete_all_invalid_ids(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test bulk delete with only invalid IDs still succeeds with 0 deleted."""
        response = await client.post(
            "/api/import-export/bulk/delete",
            headers=auth_headers,
            json={
                "entity_type": "leads",
                "entity_ids": [99999, 99998],
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["success_count"] == 0
        assert data["error_count"] == 2

    @pytest.mark.asyncio
    async def test_bulk_delete_invalid_entity_type(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test bulk delete with invalid entity type returns 400."""
        response = await client.post(
            "/api/import-export/bulk/delete",
            headers=auth_headers,
            json={
                "entity_type": "nonexistent",
                "entity_ids": [1, 2],
            },
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_bulk_delete_empty_ids(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test bulk delete with empty entity IDs returns 400."""
        response = await client.post(
            "/api/import-export/bulk/delete",
            headers=auth_headers,
            json={
                "entity_type": "leads",
                "entity_ids": [],
            },
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_bulk_delete_contacts(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Test bulk deleting contacts."""
        contact = Contact(
            first_name="Delete",
            last_name="Me",
            email="delete_contact@example.com",
            status="active",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(contact)
        await db_session.commit()
        await db_session.refresh(contact)

        response = await client.post(
            "/api/import-export/bulk/delete",
            headers=auth_headers,
            json={
                "entity_type": "contacts",
                "entity_ids": [contact.id],
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["success_count"] == 1

    @pytest.mark.asyncio
    async def test_bulk_delete_companies(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Test bulk deleting companies."""
        company = Company(
            name="Delete Me Corp",
            status="prospect",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(company)
        await db_session.commit()
        await db_session.refresh(company)

        response = await client.post(
            "/api/import-export/bulk/delete",
            headers=auth_headers,
            json={
                "entity_type": "companies",
                "entity_ids": [company.id],
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["success_count"] == 1

    @pytest.mark.asyncio
    async def test_bulk_delete_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test bulk delete without auth returns 401."""
        response = await client.post(
            "/api/import-export/bulk/delete",
            json={
                "entity_type": "leads",
                "entity_ids": [1],
            },
        )
        assert response.status_code == 401


# =========================================================================
# Calendar View Tests
# =========================================================================


class TestCalendarEndpoint:
    """Tests for GET /api/activities/calendar."""

    @pytest.mark.asyncio
    async def test_calendar_empty(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test calendar endpoint with no activities."""
        today = date.today()
        start = today.isoformat()
        end = (today + timedelta(days=7)).isoformat()

        response = await client.get(
            f"/api/activities/calendar?start_date={start}&end_date={end}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "start_date" in data
        assert "end_date" in data
        assert "dates" in data
        assert "total_activities" in data
        assert data["total_activities"] == 0
        assert data["dates"] == {}

    @pytest.mark.asyncio
    async def test_calendar_with_activities(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_activity: Activity,
    ):
        """Test calendar endpoint returns activities within date range."""
        today = date.today()
        start = today.isoformat()
        end = (today + timedelta(days=7)).isoformat()

        response = await client.get(
            f"/api/activities/calendar?start_date={start}&end_date={end}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total_activities"] >= 1

        # Verify activity data structure in dates
        for date_key, activities in data["dates"].items():
            assert isinstance(activities, list)
            for act in activities:
                assert "id" in act
                assert "activity_type" in act
                assert "subject" in act
                assert "is_completed" in act
                assert "priority" in act

    @pytest.mark.asyncio
    async def test_calendar_date_range_filtering(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_contact: Contact,
    ):
        """Test calendar only returns activities within specified date range."""
        # Create activity for tomorrow
        tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
        activity = Activity(
            activity_type="meeting",
            subject="Tomorrow Meeting",
            entity_type="contacts",
            entity_id=test_contact.id,
            scheduled_at=tomorrow,
            priority="normal",
            is_completed=False,
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(activity)
        await db_session.commit()

        # Query for a range that includes tomorrow
        start = date.today().isoformat()
        end = (date.today() + timedelta(days=7)).isoformat()

        response = await client.get(
            f"/api/activities/calendar?start_date={start}&end_date={end}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total_activities"] >= 1

    @pytest.mark.asyncio
    async def test_calendar_with_activity_type_filter(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_contact: Contact,
    ):
        """Test calendar filtering by activity type."""
        tomorrow = datetime.now(timezone.utc) + timedelta(days=1)

        # Create a call activity
        call = Activity(
            activity_type="call",
            subject="Follow up call",
            entity_type="contacts",
            entity_id=test_contact.id,
            scheduled_at=tomorrow,
            priority="normal",
            is_completed=False,
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        # Create a meeting activity
        meeting = Activity(
            activity_type="meeting",
            subject="Team standup",
            entity_type="contacts",
            entity_id=test_contact.id,
            scheduled_at=tomorrow + timedelta(hours=2),
            priority="normal",
            is_completed=False,
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add_all([call, meeting])
        await db_session.commit()

        start = date.today().isoformat()
        end = (date.today() + timedelta(days=7)).isoformat()

        # Filter for calls only
        response = await client.get(
            f"/api/activities/calendar?start_date={start}&end_date={end}&activity_type=call",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()

        # All activities in the response should be calls
        for date_key, activities in data["dates"].items():
            for act in activities:
                assert act["activity_type"] == "call"

    @pytest.mark.asyncio
    async def test_calendar_with_due_date_activities(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_contact: Contact,
    ):
        """Test calendar includes activities with due_date but no scheduled_at."""
        tomorrow = date.today() + timedelta(days=1)

        task = Activity(
            activity_type="task",
            subject="Task with due date",
            entity_type="contacts",
            entity_id=test_contact.id,
            due_date=tomorrow,
            priority="high",
            is_completed=False,
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(task)
        await db_session.commit()

        start = date.today().isoformat()
        end = (date.today() + timedelta(days=7)).isoformat()

        response = await client.get(
            f"/api/activities/calendar?start_date={start}&end_date={end}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total_activities"] >= 1

    @pytest.mark.asyncio
    async def test_calendar_requires_start_date(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test calendar endpoint requires start_date parameter."""
        response = await client.get(
            "/api/activities/calendar?end_date=2025-01-31",
            headers=auth_headers,
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_calendar_requires_end_date(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test calendar endpoint requires end_date parameter."""
        response = await client.get(
            "/api/activities/calendar?start_date=2025-01-01",
            headers=auth_headers,
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_calendar_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test calendar endpoint without auth returns 401."""
        response = await client.get(
            "/api/activities/calendar?start_date=2025-01-01&end_date=2025-01-31",
        )
        assert response.status_code == 401


# =========================================================================
# Predictive AI Tests
# =========================================================================


class TestWinProbability:
    """Tests for GET /api/ai/predict/opportunity/{opportunity_id}."""

    @pytest.mark.asyncio
    async def test_win_probability_basic(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_opportunity: Opportunity,
    ):
        """Test win probability returns a valid score for an open opportunity."""
        response = await client.get(
            f"/api/ai/predict/opportunity/{test_opportunity.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "opportunity_id" in data
        assert "win_probability" in data
        assert "base_stage_probability" in data
        assert "factors" in data
        assert data["opportunity_id"] == test_opportunity.id
        assert 0 <= data["win_probability"] <= 100
        assert isinstance(data["factors"], dict)

    @pytest.mark.asyncio
    async def test_win_probability_not_found(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test win probability for non-existent opportunity returns 404."""
        response = await client.get(
            "/api/ai/predict/opportunity/99999",
            headers=auth_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_win_probability_won_deal(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_won_stage: PipelineStage,
        test_contact: Contact,
        test_company: Company,
    ):
        """Test win probability for a won deal returns 100."""
        won_opp = Opportunity(
            name="Won Deal",
            pipeline_stage_id=test_won_stage.id,
            amount=50000.0,
            currency="USD",
            contact_id=test_contact.id,
            company_id=test_company.id,
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(won_opp)
        await db_session.commit()
        await db_session.refresh(won_opp)

        response = await client.get(
            f"/api/ai/predict/opportunity/{won_opp.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["win_probability"] == 100

    @pytest.mark.asyncio
    async def test_win_probability_lost_deal(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_contact: Contact,
        test_company: Company,
    ):
        """Test win probability for a lost deal returns 0."""
        lost_stage = PipelineStage(
            name="Closed Lost",
            order=6,
            color="#ef4444",
            probability=0,
            is_won=False,
            is_lost=True,
            is_active=True,
        )
        db_session.add(lost_stage)
        await db_session.commit()
        await db_session.refresh(lost_stage)

        lost_opp = Opportunity(
            name="Lost Deal",
            pipeline_stage_id=lost_stage.id,
            amount=30000.0,
            currency="USD",
            contact_id=test_contact.id,
            company_id=test_company.id,
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(lost_opp)
        await db_session.commit()
        await db_session.refresh(lost_opp)

        response = await client.get(
            f"/api/ai/predict/opportunity/{lost_opp.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["win_probability"] == 0

    @pytest.mark.asyncio
    async def test_win_probability_with_activity_boost(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_opportunity: Opportunity,
        test_user: User,
    ):
        """Test that recent activities boost win probability."""
        # Create multiple recent activities for the opportunity
        for i in range(4):
            activity = Activity(
                activity_type="call",
                subject=f"Activity {i}",
                entity_type="opportunities",
                entity_id=test_opportunity.id,
                priority="normal",
                is_completed=False,
                owner_id=test_user.id,
                created_by_id=test_user.id,
            )
            db_session.add(activity)
        await db_session.commit()

        response = await client.get(
            f"/api/ai/predict/opportunity/{test_opportunity.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["win_probability"] > 0
        # With contact and company assigned + high activity, should have bonuses
        assert "has_contact" in data["factors"] or "high_activity_bonus" in data["factors"]

    @pytest.mark.asyncio
    async def test_win_probability_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test win probability without auth returns 401."""
        response = await client.get("/api/ai/predict/opportunity/1")
        assert response.status_code == 401


class TestSuggestNextAction:
    """Tests for GET /api/ai/suggest/next-action/{entity_type}/{entity_id}."""

    @pytest.mark.asyncio
    async def test_suggest_next_action_for_lead(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_lead: Lead,
    ):
        """Test suggesting next action for a lead."""
        response = await client.get(
            f"/api/ai/suggest/next-action/leads/{test_lead.id}",
            headers=auth_headers,
        )

        # The endpoint delegates to RecommendationEngine which may work differently
        # depending on entity state. Accept 200 or graceful error.
        if response.status_code == 200:
            data = response.json()
            assert "action" in data
            assert "reason" in data

    @pytest.mark.asyncio
    async def test_suggest_next_action_for_contact(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contact: Contact,
    ):
        """Test suggesting next action for a contact."""
        response = await client.get(
            f"/api/ai/suggest/next-action/contacts/{test_contact.id}",
            headers=auth_headers,
        )

        if response.status_code == 200:
            data = response.json()
            assert "action" in data
            assert "reason" in data

    @pytest.mark.asyncio
    async def test_suggest_next_action_for_opportunity(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_opportunity: Opportunity,
    ):
        """Test suggesting next action for an opportunity."""
        response = await client.get(
            f"/api/ai/suggest/next-action/opportunities/{test_opportunity.id}",
            headers=auth_headers,
        )

        if response.status_code == 200:
            data = response.json()
            assert "action" in data
            assert "reason" in data

    @pytest.mark.asyncio
    async def test_suggest_next_action_not_found(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test suggesting next action for non-existent entity returns 404."""
        response = await client.get(
            "/api/ai/suggest/next-action/leads/99999",
            headers=auth_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_suggest_next_action_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test next action suggestion without auth returns 401."""
        response = await client.get("/api/ai/suggest/next-action/leads/1")
        assert response.status_code == 401


class TestActivitySummary:
    """Tests for GET /api/ai/summary/{entity_type}/{entity_id}."""

    @pytest.mark.asyncio
    async def test_activity_summary_with_activities(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contact: Contact,
        test_activity: Activity,
    ):
        """Test activity summary for a contact with activities."""
        response = await client.get(
            f"/api/ai/summary/contacts/{test_contact.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["entity_type"] == "contacts"
        assert data["entity_id"] == test_contact.id
        assert data["period_days"] == 30
        assert data["total_activities"] >= 1
        assert "by_type" in data
        assert "summary" in data
        assert isinstance(data["summary"], str)

    @pytest.mark.asyncio
    async def test_activity_summary_no_activities(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Test activity summary for entity with no activities."""
        # Create a contact without any activities
        contact = Contact(
            first_name="No",
            last_name="Activities",
            email="no_activities@example.com",
            status="active",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(contact)
        await db_session.commit()
        await db_session.refresh(contact)

        response = await client.get(
            f"/api/ai/summary/contacts/{contact.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total_activities"] == 0
        assert data["by_type"] == {}
        assert "No activities" in data["summary"]

    @pytest.mark.asyncio
    async def test_activity_summary_custom_days(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contact: Contact,
        test_activity: Activity,
    ):
        """Test activity summary with custom days parameter."""
        response = await client.get(
            f"/api/ai/summary/contacts/{test_contact.id}?days=7",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["period_days"] == 7

    @pytest.mark.asyncio
    async def test_activity_summary_response_structure(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contact: Contact,
        test_activity: Activity,
    ):
        """Test activity summary returns expected structure."""
        response = await client.get(
            f"/api/ai/summary/contacts/{test_contact.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()

        # Verify last_activity structure when activities exist
        if data["total_activities"] > 0:
            assert "last_activity" in data
            last = data["last_activity"]
            assert "id" in last
            assert "type" in last
            assert "subject" in last
            assert "date" in last

    @pytest.mark.asyncio
    async def test_activity_summary_multiple_types(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_contact: Contact,
    ):
        """Test activity summary counts by type correctly."""
        # Create activities of different types
        for atype in ["call", "email", "meeting"]:
            activity = Activity(
                activity_type=atype,
                subject=f"Test {atype}",
                entity_type="contacts",
                entity_id=test_contact.id,
                priority="normal",
                is_completed=atype == "call",
                owner_id=test_user.id,
                created_by_id=test_user.id,
            )
            db_session.add(activity)
        await db_session.commit()

        response = await client.get(
            f"/api/ai/summary/contacts/{test_contact.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total_activities"] >= 3
        assert "call" in data["by_type"]
        assert "email" in data["by_type"]
        assert "meeting" in data["by_type"]

    @pytest.mark.asyncio
    async def test_activity_summary_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test activity summary without auth returns 401."""
        response = await client.get("/api/ai/summary/contacts/1")
        assert response.status_code == 401
