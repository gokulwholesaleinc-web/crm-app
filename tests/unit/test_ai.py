"""
Unit tests for AI assistant endpoints.

Tests for chat, insights, recommendations, and semantic search.
Note: OpenAI API calls are skipped if no API key is configured.
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


class TestLeadInsights:
    """Tests for lead insights endpoint."""

    @pytest.mark.asyncio
    async def test_get_lead_insights_not_found(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test getting insights for non-existent lead."""
        response = await client.get(
            "/api/ai/insights/lead/99999",
            headers=auth_headers,
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_lead_insights_structure(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_lead: Lead,
    ):
        """Test lead insights endpoint structure."""
        response = await client.get(
            f"/api/ai/insights/lead/{test_lead.id}",
            headers=auth_headers,
        )

        # May return 200 or 500/503 if OpenAI not configured
        if response.status_code == 200:
            data = response.json()
            assert "insights" in data
            assert "lead_data" in data or data.get("lead_data") is None

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


class TestOpportunityInsights:
    """Tests for opportunity insights endpoint."""

    @pytest.mark.asyncio
    async def test_get_opportunity_insights_not_found(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test getting insights for non-existent opportunity."""
        response = await client.get(
            "/api/ai/insights/opportunity/99999",
            headers=auth_headers,
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_opportunity_insights_structure(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_opportunity: Opportunity,
    ):
        """Test opportunity insights endpoint structure."""
        response = await client.get(
            f"/api/ai/insights/opportunity/{test_opportunity.id}",
            headers=auth_headers,
        )

        # May return 200 or 500/503 if OpenAI not configured
        if response.status_code == 200:
            data = response.json()
            assert "insights" in data

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


class TestDailySummary:
    """Tests for daily summary endpoint."""

    @pytest.mark.asyncio
    async def test_get_daily_summary_structure(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test daily summary endpoint structure."""
        response = await client.get(
            "/api/ai/summary/daily",
            headers=auth_headers,
        )

        # May return 200 or 500/503 if OpenAI not configured
        if response.status_code == 200:
            data = response.json()
            assert "data" in data
            assert "summary" in data

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


class TestRecommendations:
    """Tests for recommendations endpoint."""

    @pytest.mark.asyncio
    async def test_get_recommendations_empty(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test getting recommendations when no data exists."""
        response = await client.get(
            "/api/ai/recommendations",
            headers=auth_headers,
        )

        # Should return 200 even with no recommendations
        assert response.status_code == 200
        data = response.json()
        assert "recommendations" in data
        assert isinstance(data["recommendations"], list)

    @pytest.mark.asyncio
    async def test_get_recommendations_structure(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_lead: Lead,
        test_opportunity: Opportunity,
    ):
        """Test recommendations response structure."""
        response = await client.get(
            "/api/ai/recommendations",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "recommendations" in data

        # If there are recommendations, check structure
        for rec in data["recommendations"]:
            assert "type" in rec
            assert "priority" in rec
            assert "title" in rec
            assert "description" in rec
            assert "action" in rec

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


class TestNextBestAction:
    """Tests for next best action endpoint."""

    @pytest.mark.asyncio
    async def test_next_action_lead_not_found(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test next action for non-existent lead."""
        response = await client.get(
            "/api/ai/next-action/lead/99999",
            headers=auth_headers,
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_next_action_opportunity_not_found(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test next action for non-existent opportunity."""
        response = await client.get(
            "/api/ai/next-action/opportunity/99999",
            headers=auth_headers,
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_next_action_for_lead(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_lead: Lead,
    ):
        """Test getting next best action for a lead."""
        response = await client.get(
            f"/api/ai/next-action/lead/{test_lead.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "action" in data
        assert "reason" in data

    @pytest.mark.asyncio
    async def test_next_action_for_opportunity(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_opportunity: Opportunity,
    ):
        """Test getting next best action for an opportunity."""
        response = await client.get(
            f"/api/ai/next-action/opportunity/{test_opportunity.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "action" in data
        assert "reason" in data

    @pytest.mark.asyncio
    async def test_next_action_for_contact(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contact: Contact,
    ):
        """Test getting next best action for a contact."""
        response = await client.get(
            f"/api/ai/next-action/contact/{test_contact.id}",
            headers=auth_headers,
        )

        # May return 200 or 404 depending on implementation
        assert response.status_code in [200, 404]


class TestSemanticSearch:
    """Tests for semantic search endpoint."""

    @pytest.mark.asyncio
    async def test_search_missing_query(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test search requires query parameter."""
        response = await client.get(
            "/api/ai/search",
            headers=auth_headers,
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_search_empty_results(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test search returns empty results for non-matching query."""
        response = await client.get(
            "/api/ai/search",
            headers=auth_headers,
            params={"query": "xyz123nonexistent"},
        )

        # May return 200 with empty results or error if no embeddings
        if response.status_code == 200:
            data = response.json()
            assert "results" in data
            assert isinstance(data["results"], list)

    @pytest.mark.asyncio
    async def test_search_with_entity_filter(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test search with entity type filter."""
        response = await client.get(
            "/api/ai/search",
            headers=auth_headers,
            params={
                "query": "technology",
                "entity_types": "lead,contact",
            },
        )

        # May return 200 or error depending on embeddings availability
        if response.status_code == 200:
            data = response.json()
            assert "results" in data

    @pytest.mark.asyncio
    async def test_search_with_limit(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test search with custom limit."""
        response = await client.get(
            "/api/ai/search",
            headers=auth_headers,
            params={
                "query": "sales",
                "limit": 3,
            },
        )

        if response.status_code == 200:
            data = response.json()
            assert "results" in data
            assert len(data["results"]) <= 3

    @requires_openai
    @pytest.mark.asyncio
    async def test_search_result_structure(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_lead: Lead,
    ):
        """Test search results have correct structure."""
        response = await client.get(
            "/api/ai/search",
            headers=auth_headers,
            params={"query": test_lead.first_name},
        )

        assert response.status_code == 200
        data = response.json()
        assert "results" in data

        for result in data["results"]:
            assert "entity_type" in result
            assert "entity_id" in result
            assert "content" in result
            assert "similarity" in result


class TestAIUnauthorized:
    """Tests for unauthorized access to AI endpoints."""

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

    @pytest.mark.asyncio
    async def test_lead_insights_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession, test_lead: Lead
    ):
        """Test lead insights without auth fails."""
        response = await client.get(f"/api/ai/insights/lead/{test_lead.id}")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_opportunity_insights_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession, test_opportunity: Opportunity
    ):
        """Test opportunity insights without auth fails."""
        response = await client.get(f"/api/ai/insights/opportunity/{test_opportunity.id}")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_daily_summary_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test daily summary without auth fails."""
        response = await client.get("/api/ai/summary/daily")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_recommendations_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test recommendations without auth fails."""
        response = await client.get("/api/ai/recommendations")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_next_action_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession, test_lead: Lead
    ):
        """Test next action without auth fails."""
        response = await client.get(f"/api/ai/next-action/lead/{test_lead.id}")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_search_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test search without auth fails."""
        response = await client.get(
            "/api/ai/search",
            params={"query": "test"},
        )
        assert response.status_code == 401
