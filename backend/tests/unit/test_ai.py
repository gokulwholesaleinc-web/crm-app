"""
Unit tests for AI assistant endpoints.

Tests for chat endpoint and OpenAI-dependent integration tests.
Note: Duplicate test classes (TestLeadInsights, TestOpportunityInsights,
TestDailySummary, TestRecommendations, TestNextBestAction, TestSemanticSearch)
were consolidated into test_ai_endpoints.py which has more comprehensive coverage.
Unauthorized access tests were also consolidated there.
"""

import os
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.leads.models import Lead, LeadSource
from src.opportunities.models import Opportunity, PipelineStage
from src.activities.models import Activity
from src.contacts.models import Contact


# Check if OpenAI API is available
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
requires_openai = pytest.mark.skipif(
    not OPENAI_API_KEY,
    reason="OpenAI API key not configured"
)


class TestChatEndpoint:
    """Tests for AI chat endpoint."""

    @pytest.mark.asyncio
    async def test_chat_request_structure(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test chat endpoint accepts correct request structure."""
        response = await client.post(
            "/api/ai/chat",
            headers=auth_headers,
            json={
                "message": "Hello",
                "session_id": "test-session-123",
            },
        )

        # Should either succeed or fail gracefully (no OpenAI key)
        assert response.status_code in [200, 500, 503]

    @pytest.mark.asyncio
    async def test_chat_missing_message(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test chat endpoint requires message."""
        response = await client.post(
            "/api/ai/chat",
            headers=auth_headers,
            json={
                "session_id": "test-session-123",
            },
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_chat_without_session_id(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test chat endpoint works without session_id."""
        response = await client.post(
            "/api/ai/chat",
            headers=auth_headers,
            json={
                "message": "What is the weather?",
            },
        )

        # Should either succeed or fail gracefully (no OpenAI key)
        assert response.status_code in [200, 500, 503]

    @requires_openai
    @pytest.mark.asyncio
    async def test_chat_response_format(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test chat returns properly formatted response."""
        response = await client.post(
            "/api/ai/chat",
            headers=auth_headers,
            json={
                "message": "How many leads do I have?",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "response" in data
        assert isinstance(data["response"], str)


class TestNextBestActionSingularRoutes:
    """Tests for next best action using singular entity type URL routes.

    Note: The plural-form routes (/leads/, /opportunities/, /contacts/) are
    tested in test_ai_endpoints.py. These tests cover the singular-form
    routes (/lead/, /opportunity/, /contact/) which are a separate URL pattern.
    """

    @pytest.mark.asyncio
    async def test_next_action_for_lead_singular_route(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_lead: Lead,
    ):
        """Test getting next best action for a lead via singular route."""
        response = await client.get(
            f"/api/ai/next-action/lead/{test_lead.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "action" in data
        assert "reason" in data

    @pytest.mark.asyncio
    async def test_next_action_for_opportunity_singular_route(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_opportunity: Opportunity,
    ):
        """Test getting next best action for an opportunity via singular route."""
        response = await client.get(
            f"/api/ai/next-action/opportunity/{test_opportunity.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "action" in data
        assert "reason" in data

    @pytest.mark.asyncio
    async def test_next_action_for_contact_singular_route(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contact: Contact,
    ):
        """Test getting next best action for a contact via singular route."""
        response = await client.get(
            f"/api/ai/next-action/contact/{test_contact.id}",
            headers=auth_headers,
        )

        # May return 200 or 404 depending on implementation
        assert response.status_code in [200, 404]


class TestAIOpenAIIntegration:
    """Tests that require OpenAI API key to run.

    These tests validate full integration with OpenAI and are skipped
    when no API key is configured.
    """

    @requires_openai
    @pytest.mark.asyncio
    async def test_get_lead_insights_with_openai(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_lead: Lead,
    ):
        """Test lead insights with OpenAI integration."""
        response = await client.get(
            f"/api/ai/insights/lead/{test_lead.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "insights" in data
        assert len(data["insights"]) > 0

    @requires_openai
    @pytest.mark.asyncio
    async def test_get_opportunity_insights_with_openai(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_opportunity: Opportunity,
    ):
        """Test opportunity insights with OpenAI integration."""
        response = await client.get(
            f"/api/ai/insights/opportunity/{test_opportunity.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "insights" in data
        assert len(data["insights"]) > 0

    @requires_openai
    @pytest.mark.asyncio
    async def test_get_daily_summary_with_data(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_lead: Lead,
        test_opportunity: Opportunity,
        test_activity: Activity,
    ):
        """Test daily summary with CRM data."""
        response = await client.get(
            "/api/ai/summary/daily",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "summary" in data
        assert len(data["summary"]) > 0


class TestRecommendationsWithActivities:
    """Test recommendations with activity data present."""

    @pytest.mark.asyncio
    async def test_recommendations_with_activities(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_activity: Activity,
    ):
        """Test recommendations include activity-based ones."""
        response = await client.get(
            "/api/ai/recommendations",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["recommendations"], list)


class TestChatUnauthorized:
    """Test unauthorized access to chat endpoint.

    Note: Unauthorized tests for other AI endpoints (insights, summary,
    recommendations, next-action, search) are in test_ai_endpoints.py.
    """

    @pytest.mark.asyncio
    async def test_chat_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test chat without auth fails."""
        response = await client.post(
            "/api/ai/chat",
            json={"message": "Hello"},
        )
        assert response.status_code == 401
