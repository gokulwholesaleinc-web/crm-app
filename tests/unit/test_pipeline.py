"""
Unit tests for Phase 6: Sales Pipeline Integration.

Tests for:
- Dashboard sales KPI endpoint
- Event constants for sales pipeline
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.opportunities.models import Opportunity, PipelineStage
from src.quotes.models import Quote
from src.proposals.models import Proposal
from src.payments.models import Payment, StripeCustomer
from src.events.service import (
    QUOTE_SENT,
    QUOTE_ACCEPTED,
    PROPOSAL_SENT,
    PROPOSAL_ACCEPTED,
    PAYMENT_RECEIVED,
)


class TestSalesEventConstants:
    """Tests to verify sales pipeline event constants exist."""

    def test_quote_sent_event_exists(self):
        """Test QUOTE_SENT event constant is defined."""
        assert QUOTE_SENT == "quote.sent"

    def test_quote_accepted_event_exists(self):
        """Test QUOTE_ACCEPTED event constant is defined."""
        assert QUOTE_ACCEPTED == "quote.accepted"

    def test_proposal_sent_event_exists(self):
        """Test PROPOSAL_SENT event constant is defined."""
        assert PROPOSAL_SENT == "proposal.sent"

    def test_proposal_accepted_event_exists(self):
        """Test PROPOSAL_ACCEPTED event constant is defined."""
        assert PROPOSAL_ACCEPTED == "proposal.accepted"

    def test_payment_received_event_exists(self):
        """Test PAYMENT_RECEIVED event constant is defined."""
        assert PAYMENT_RECEIVED == "payment.received"


class TestSalesKPIsEndpoint:
    """Tests for the GET /api/dashboard/sales-kpis endpoint."""

    @pytest.mark.asyncio
    async def test_sales_kpis_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test that sales KPIs endpoint requires authentication."""
        response = await client.get("/api/dashboard/sales-kpis")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_sales_kpis_empty(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test sales KPIs when no data exists."""
        response = await client.get(
            "/api/dashboard/sales-kpis", headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "quotes_sent" in data
        assert "proposals_sent" in data
        assert "payments_collected_total" in data
        assert "payments_collected_count" in data
        assert "quote_to_payment_conversion_rate" in data
        assert data["quotes_sent"] == 0
        assert data["proposals_sent"] == 0
        assert data["payments_collected_total"] == 0.0
        assert data["payments_collected_count"] == 0
        assert data["quote_to_payment_conversion_rate"] == 0.0

    @pytest.mark.asyncio
    async def test_sales_kpis_with_quotes(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_opportunity: Opportunity,
    ):
        """Test sales KPIs reflect quote counts correctly."""
        # Create a draft quote (should NOT count as sent)
        draft_quote = Quote(
            title="Draft Quote",
            quote_number="Q-DRAFT-001",
            status="draft",
            subtotal=1000.0,
            total=1000.0,
            currency="USD",
            opportunity_id=test_opportunity.id,
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(draft_quote)

        # Create a sent quote (should count)
        sent_quote = Quote(
            title="Sent Quote",
            quote_number="Q-SENT-001",
            status="sent",
            subtotal=2000.0,
            total=2000.0,
            currency="USD",
            opportunity_id=test_opportunity.id,
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(sent_quote)

        # Create an accepted quote
        accepted_quote = Quote(
            title="Accepted Quote",
            quote_number="Q-ACC-001",
            status="accepted",
            subtotal=5000.0,
            total=5000.0,
            currency="USD",
            opportunity_id=test_opportunity.id,
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(accepted_quote)

        await db_session.commit()

        response = await client.get(
            "/api/dashboard/sales-kpis", headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()

        # 2 quotes that are not draft (sent + accepted)
        assert data["quotes_sent"] == 2
        # 1 out of 3 total quotes is accepted = 33.3%
        assert data["quote_to_payment_conversion_rate"] == 33.3

    @pytest.mark.asyncio
    async def test_sales_kpis_with_proposals(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_opportunity: Opportunity,
    ):
        """Test sales KPIs reflect proposal counts correctly."""
        # Create a sent proposal
        sent_proposal = Proposal(
            title="Sent Proposal",
            proposal_number="P-SENT-001",
            status="sent",
            content="Test content",
            opportunity_id=test_opportunity.id,
            created_by_id=test_user.id,
        )
        db_session.add(sent_proposal)

        # Draft proposal (should NOT count as sent)
        draft_proposal = Proposal(
            title="Draft Proposal",
            proposal_number="P-DRAFT-001",
            status="draft",
            content="Test content",
            opportunity_id=test_opportunity.id,
            created_by_id=test_user.id,
        )
        db_session.add(draft_proposal)

        await db_session.commit()

        response = await client.get(
            "/api/dashboard/sales-kpis", headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["proposals_sent"] == 1

    @pytest.mark.asyncio
    async def test_sales_kpis_with_payments(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Test sales KPIs reflect payment totals correctly."""
        # Create a Stripe customer first
        customer = StripeCustomer(
            email="pay@test.com",
            name="Test Payer",
            stripe_customer_id="cus_test123",
        )
        db_session.add(customer)
        await db_session.flush()

        # Create succeeded payment
        payment1 = Payment(
            amount=15000,
            currency="usd",
            status="succeeded",
            stripe_payment_intent_id="pi_test_001",
            customer_id=customer.id,
        )
        db_session.add(payment1)

        payment2 = Payment(
            amount=25000,
            currency="usd",
            status="succeeded",
            stripe_payment_intent_id="pi_test_002",
            customer_id=customer.id,
        )
        db_session.add(payment2)

        # Failed payment (should NOT count)
        payment_failed = Payment(
            amount=5000,
            currency="usd",
            status="failed",
            stripe_payment_intent_id="pi_test_003",
            customer_id=customer.id,
        )
        db_session.add(payment_failed)

        await db_session.commit()

        response = await client.get(
            "/api/dashboard/sales-kpis", headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["payments_collected_count"] == 2
        assert data["payments_collected_total"] == 40000.0

    @pytest.mark.asyncio
    async def test_sales_kpis_response_structure(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test that sales KPIs response has correct field types."""
        response = await client.get(
            "/api/dashboard/sales-kpis", headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()

        assert isinstance(data["quotes_sent"], int)
        assert isinstance(data["proposals_sent"], int)
        assert isinstance(data["payments_collected_total"], (int, float))
        assert isinstance(data["payments_collected_count"], int)
        assert isinstance(data["quote_to_payment_conversion_rate"], (int, float))
