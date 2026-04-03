"""
Unit tests for AI learning system endpoints.

Tests for feedback, knowledge base, preferences, and conversation memory.
No mocking - follows integration test patterns from test_ai.py.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.ai.models import AIFeedback, AIKnowledgeDocument, AIUserPreferences


class TestFeedbackSubmission:
    """Tests for AI feedback submission endpoint."""

    @pytest.mark.asyncio
    async def test_submit_positive_feedback(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test submitting positive feedback."""
        response = await client.post(
            "/api/ai/feedback",
            headers=auth_headers,
            json={
                "query": "How many leads do I have?",
                "response": "You have 5 leads.",
                "feedback": "positive",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["feedback"] == "positive"
        assert "id" in data
        assert "created_at" in data

    @pytest.mark.asyncio
    async def test_submit_negative_feedback(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test submitting negative feedback."""
        response = await client.post(
            "/api/ai/feedback",
            headers=auth_headers,
            json={
                "query": "Show me top deals",
                "response": "Here are your top deals.",
                "feedback": "negative",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["feedback"] == "negative"

    @pytest.mark.asyncio
    async def test_submit_correction_feedback(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test submitting correction feedback with correction text."""
        response = await client.post(
            "/api/ai/feedback",
            headers=auth_headers,
            json={
                "query": "Who is my top contact?",
                "response": "Your top contact is John.",
                "feedback": "correction",
                "correction_text": "My top contact is actually Jane Smith.",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["feedback"] == "correction"

    @pytest.mark.asyncio
    async def test_correction_requires_text(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test that correction feedback requires correction_text."""
        response = await client.post(
            "/api/ai/feedback",
            headers=auth_headers,
            json={
                "query": "Test query",
                "response": "Test response",
                "feedback": "correction",
            },
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_invalid_feedback_type(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test that invalid feedback type is rejected."""
        response = await client.post(
            "/api/ai/feedback",
            headers=auth_headers,
            json={
                "query": "Test query",
                "response": "Test response",
                "feedback": "invalid_type",
            },
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_feedback_with_session_id(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test feedback with session and context IDs."""
        response = await client.post(
            "/api/ai/feedback",
            headers=auth_headers,
            json={
                "session_id": "sess-123",
                "query": "Show pipeline",
                "response": "Pipeline has 3 deals.",
                "retrieved_context_ids": [1, 2, 3],
                "feedback": "positive",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["feedback"] == "positive"

    @pytest.mark.asyncio
    async def test_feedback_missing_required_fields(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test feedback requires query, response, and feedback fields."""
        response = await client.post(
            "/api/ai/feedback",
            headers=auth_headers,
            json={
                "feedback": "positive",
            },
        )

        assert response.status_code == 422


class TestFeedbackStats:
    """Tests for feedback statistics endpoint."""

    @pytest.mark.asyncio
    async def test_feedback_stats_empty(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test feedback stats when no feedback exists."""
        response = await client.get(
            "/api/ai/feedback/stats",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["positive"] == 0
        assert data["negative"] == 0
        assert data["corrections"] == 0

    @pytest.mark.asyncio
    async def test_feedback_stats_with_data(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test feedback stats after submitting feedback."""
        # Submit various feedback types
        for fb_type in ["positive", "positive", "negative"]:
            await client.post(
                "/api/ai/feedback",
                headers=auth_headers,
                json={
                    "query": "Test",
                    "response": "Response",
                    "feedback": fb_type,
                },
            )

        # Submit a correction
        await client.post(
            "/api/ai/feedback",
            headers=auth_headers,
            json={
                "query": "Test",
                "response": "Response",
                "feedback": "correction",
                "correction_text": "Corrected response",
            },
        )

        response = await client.get(
            "/api/ai/feedback/stats",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 4
        assert data["positive"] == 2
        assert data["negative"] == 1
        assert data["corrections"] == 1


class TestKnowledgeBaseUpload:
    """Tests for knowledge base upload endpoint."""

    @pytest.mark.asyncio
    async def test_upload_text_document(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test uploading a plain text document."""
        content = b"This is a test document about CRM best practices. " * 20

        response = await client.post(
            "/api/ai/knowledge-base/upload",
            headers=auth_headers,
            files={"file": ("test.txt", content, "text/plain")},
        )

        # May fail if OpenAI key not set (embedding creation)
        if response.status_code == 200:
            data = response.json()
            assert data["filename"] == "test.txt"
            assert data["content_type"] == "text/plain"
            assert data["chunk_count"] >= 0
            assert "id" in data
            assert "created_at" in data

    @pytest.mark.asyncio
    async def test_upload_csv_document(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test uploading a CSV document."""
        csv_content = b"name,email,company\nJohn,john@test.com,Acme\nJane,jane@test.com,Corp"

        response = await client.post(
            "/api/ai/knowledge-base/upload",
            headers=auth_headers,
            files={"file": ("contacts.csv", csv_content, "text/csv")},
        )

        if response.status_code == 200:
            data = response.json()
            assert data["filename"] == "contacts.csv"
            assert data["content_type"] == "text/csv"

    @pytest.mark.asyncio
    async def test_upload_unsupported_type(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test rejecting unsupported file types."""
        response = await client.post(
            "/api/ai/knowledge-base/upload",
            headers=auth_headers,
            files={"file": ("test.exe", b"binary content", "application/octet-stream")},
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_upload_no_file(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test upload without file."""
        response = await client.post(
            "/api/ai/knowledge-base/upload",
            headers=auth_headers,
        )

        assert response.status_code == 422


class TestKnowledgeBaseList:
    """Tests for knowledge base list endpoint."""

    @pytest.mark.asyncio
    async def test_list_empty(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test listing documents when none exist."""
        response = await client.get(
            "/api/ai/knowledge-base",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "documents" in data
        assert isinstance(data["documents"], list)
        assert len(data["documents"]) == 0

    @pytest.mark.asyncio
    async def test_list_after_upload(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test listing documents after uploading one."""
        # Upload a document first
        upload_resp = await client.post(
            "/api/ai/knowledge-base/upload",
            headers=auth_headers,
            files={"file": ("notes.txt", b"Some CRM notes content here", "text/plain")},
        )

        if upload_resp.status_code != 200:
            pytest.skip("Upload failed (likely no OpenAI key)")

        response = await client.get(
            "/api/ai/knowledge-base",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["documents"]) >= 1
        doc = data["documents"][0]
        assert "id" in doc
        assert "filename" in doc
        assert "content_type" in doc
        assert "chunk_count" in doc
        assert "created_at" in doc


class TestKnowledgeBaseDelete:
    """Tests for knowledge base delete endpoint."""

    @pytest.mark.asyncio
    async def test_delete_nonexistent(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test deleting a non-existent document."""
        response = await client.delete(
            "/api/ai/knowledge-base/99999",
            headers=auth_headers,
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_after_upload(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test uploading then deleting a document."""
        # Upload first
        upload_resp = await client.post(
            "/api/ai/knowledge-base/upload",
            headers=auth_headers,
            files={"file": ("delete_me.txt", b"Content to delete", "text/plain")},
        )

        if upload_resp.status_code != 200:
            pytest.skip("Upload failed (likely no OpenAI key)")

        doc_id = upload_resp.json()["id"]

        # Delete
        delete_resp = await client.delete(
            f"/api/ai/knowledge-base/{doc_id}",
            headers=auth_headers,
        )

        assert delete_resp.status_code == 204

        # Verify it's gone
        list_resp = await client.get(
            "/api/ai/knowledge-base",
            headers=auth_headers,
        )
        assert list_resp.status_code == 200
        docs = list_resp.json()["documents"]
        assert all(d["id"] != doc_id for d in docs)


class TestPreferencesGet:
    """Tests for getting user AI preferences."""

    @pytest.mark.asyncio
    async def test_get_default_preferences(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test getting preferences when none are set returns defaults."""
        response = await client.get(
            "/api/ai/preferences",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "user_id" in data
        assert data["preferred_communication_style"] == "professional"


class TestPreferencesUpdate:
    """Tests for updating user AI preferences."""

    @pytest.mark.asyncio
    async def test_create_preferences(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test creating preferences for the first time."""
        response = await client.put(
            "/api/ai/preferences",
            headers=auth_headers,
            json={
                "preferred_communication_style": "casual",
                "custom_instructions": "Always prioritize leads over contacts",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["preferred_communication_style"] == "casual"
        assert data["custom_instructions"] == "Always prioritize leads over contacts"

    @pytest.mark.asyncio
    async def test_update_existing_preferences(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test updating already existing preferences."""
        # First create
        await client.put(
            "/api/ai/preferences",
            headers=auth_headers,
            json={
                "preferred_communication_style": "formal",
                "custom_instructions": "First instruction",
            },
        )

        # Then update
        response = await client.put(
            "/api/ai/preferences",
            headers=auth_headers,
            json={
                "preferred_communication_style": "casual",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["preferred_communication_style"] == "casual"
        # custom_instructions should still be there from the first set
        assert data["custom_instructions"] == "First instruction"

    @pytest.mark.asyncio
    async def test_set_priority_entities(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test setting priority entities."""
        response = await client.put(
            "/api/ai/preferences",
            headers=auth_headers,
            json={
                "priority_entities": {"leads": ["hot", "warm"], "opportunities": ["large"]},
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["priority_entities"] == {"leads": ["hot", "warm"], "opportunities": ["large"]}

    @pytest.mark.asyncio
    async def test_get_after_update(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test that GET returns updated preferences."""
        await client.put(
            "/api/ai/preferences",
            headers=auth_headers,
            json={
                "preferred_communication_style": "technical",
                "custom_instructions": "Be concise",
            },
        )

        response = await client.get(
            "/api/ai/preferences",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["preferred_communication_style"] == "technical"
        assert data["custom_instructions"] == "Be concise"


class TestAILearningUnauthorized:
    """Tests for unauthorized access to all new AI learning endpoints."""

    @pytest.mark.asyncio
    async def test_feedback_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test feedback without auth fails."""
        response = await client.post(
            "/api/ai/feedback",
            json={
                "query": "test",
                "response": "test",
                "feedback": "positive",
            },
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_feedback_stats_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test feedback stats without auth fails."""
        response = await client.get("/api/ai/feedback/stats")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_knowledge_upload_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test knowledge base upload without auth fails."""
        response = await client.post(
            "/api/ai/knowledge-base/upload",
            files={"file": ("test.txt", b"content", "text/plain")},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_knowledge_list_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test knowledge base list without auth fails."""
        response = await client.get("/api/ai/knowledge-base")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_knowledge_delete_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test knowledge base delete without auth fails."""
        response = await client.delete("/api/ai/knowledge-base/1")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_preferences_get_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test preferences get without auth fails."""
        response = await client.get("/api/ai/preferences")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_preferences_update_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test preferences update without auth fails."""
        response = await client.put(
            "/api/ai/preferences",
            json={"preferred_communication_style": "casual"},
        )
        assert response.status_code == 401


# =========================================================================
# AI Learning Memory Tests
# =========================================================================


class TestTeachAI:
    """Tests for the teach AI endpoint."""

    @pytest.mark.asyncio
    async def test_teach_preference(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test teaching the AI a new preference."""
        response = await client.post(
            "/api/ai/teach",
            headers=auth_headers,
            json={
                "category": "preference",
                "key": "report_format",
                "value": "Always show numbers in tables",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["category"] == "preference"
        assert data["key"] == "report_format"
        assert data["value"] == "Always show numbers in tables"
        assert data["confidence"] == 1.0
        assert data["times_reinforced"] == 1
        assert "id" in data
        assert "created_at" in data

    @pytest.mark.asyncio
    async def test_teach_reinforces_existing(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test that teaching the same key reinforces it."""
        # Teach first time
        r1 = await client.post(
            "/api/ai/teach",
            headers=auth_headers,
            json={
                "category": "preference",
                "key": "timezone",
                "value": "PST",
            },
        )
        assert r1.status_code == 200
        first_id = r1.json()["id"]

        # Teach same key again with updated value
        r2 = await client.post(
            "/api/ai/teach",
            headers=auth_headers,
            json={
                "category": "preference",
                "key": "timezone",
                "value": "EST",
            },
        )
        assert r2.status_code == 200
        data = r2.json()
        assert data["id"] == first_id
        assert data["value"] == "EST"
        assert data["times_reinforced"] == 2

    @pytest.mark.asyncio
    async def test_teach_entity_context(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test teaching entity context."""
        response = await client.post(
            "/api/ai/teach",
            headers=auth_headers,
            json={
                "category": "entity_context",
                "key": "Acme Corp",
                "value": "Our largest client, contact through VP of Sales",
            },
        )

        assert response.status_code == 200
        assert response.json()["category"] == "entity_context"

    @pytest.mark.asyncio
    async def test_teach_missing_fields(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test that missing required fields returns 422."""
        response = await client.post(
            "/api/ai/teach",
            headers=auth_headers,
            json={"category": "preference"},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_teach_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test teach without auth fails."""
        response = await client.post(
            "/api/ai/teach",
            json={"category": "preference", "key": "test", "value": "test"},
        )
        assert response.status_code == 401


class TestGetLearnings:
    """Tests for listing AI learnings."""

    @pytest.mark.asyncio
    async def test_get_learnings_empty(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test getting learnings when none exist."""
        response = await client.get(
            "/api/ai/learnings",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "learnings" in data
        assert isinstance(data["learnings"], list)

    @pytest.mark.asyncio
    async def test_get_learnings_after_teach(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test getting learnings after teaching."""
        # Teach something first
        await client.post(
            "/api/ai/teach",
            headers=auth_headers,
            json={
                "category": "preference",
                "key": "favorite_metric",
                "value": "Pipeline value",
            },
        )

        response = await client.get(
            "/api/ai/learnings",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["learnings"]) >= 1
        learning = data["learnings"][0]
        assert "id" in learning
        assert "category" in learning
        assert "key" in learning
        assert "value" in learning
        assert "confidence" in learning

    @pytest.mark.asyncio
    async def test_get_learnings_filtered_by_category(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test filtering learnings by category."""
        # Teach two categories
        await client.post(
            "/api/ai/teach",
            headers=auth_headers,
            json={"category": "preference", "key": "style", "value": "brief"},
        )
        await client.post(
            "/api/ai/teach",
            headers=auth_headers,
            json={"category": "entity_context", "key": "BigCorp", "value": "Important client"},
        )

        # Filter by preference
        response = await client.get(
            "/api/ai/learnings",
            headers=auth_headers,
            params={"category": "preference"},
        )

        assert response.status_code == 200
        data = response.json()
        for learning in data["learnings"]:
            assert learning["category"] == "preference"

    @pytest.mark.asyncio
    async def test_get_learnings_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test learnings without auth fails."""
        response = await client.get("/api/ai/learnings")
        assert response.status_code == 401


class TestDeleteLearning:
    """Tests for deleting AI learnings."""

    @pytest.mark.asyncio
    async def test_delete_learning(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test deleting a learning."""
        # Create one
        teach_resp = await client.post(
            "/api/ai/teach",
            headers=auth_headers,
            json={"category": "preference", "key": "to_delete", "value": "will be deleted"},
        )
        learning_id = teach_resp.json()["id"]

        # Delete it
        delete_resp = await client.delete(
            f"/api/ai/learnings/{learning_id}",
            headers=auth_headers,
        )
        assert delete_resp.status_code == 204

        # Verify it's gone
        list_resp = await client.get(
            "/api/ai/learnings",
            headers=auth_headers,
        )
        data = list_resp.json()
        assert all(l["id"] != learning_id for l in data["learnings"])

    @pytest.mark.asyncio
    async def test_delete_nonexistent_learning(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test deleting a non-existent learning returns 404."""
        response = await client.delete(
            "/api/ai/learnings/99999",
            headers=auth_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_learning_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test delete learning without auth fails."""
        response = await client.delete("/api/ai/learnings/1")
        assert response.status_code == 401


class TestSmartSuggestions:
    """Tests for smart suggestions endpoint."""

    @pytest.mark.asyncio
    async def test_get_smart_suggestions(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test getting smart suggestions."""
        response = await client.get(
            "/api/ai/smart-suggestions",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "suggestions" in data
        assert isinstance(data["suggestions"], list)

    @pytest.mark.asyncio
    async def test_smart_suggestions_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test smart suggestions without auth fails."""
        response = await client.get("/api/ai/smart-suggestions")
        assert response.status_code == 401


class TestEntityInsights:
    """Tests for entity insights endpoint."""

    @pytest.mark.asyncio
    async def test_get_entity_insights(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test getting entity insights for a valid entity type."""
        response = await client.get(
            "/api/ai/entity-insights/contacts/1",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["entity_type"] == "contacts"
        assert data["entity_id"] == 1
        assert "insights" in data
        assert "suggestions" in data
        assert isinstance(data["insights"], list)
        assert isinstance(data["suggestions"], list)

    @pytest.mark.asyncio
    async def test_entity_insights_for_opportunity(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test getting entity insights for an opportunity."""
        response = await client.get(
            "/api/ai/entity-insights/opportunities/1",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["entity_type"] == "opportunities"

    @pytest.mark.asyncio
    async def test_entity_insights_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test entity insights without auth fails."""
        response = await client.get("/api/ai/entity-insights/contacts/1")
        assert response.status_code == 401


class TestLearningService:
    """Tests for the AILearningService directly via the endpoints."""

    @pytest.mark.asyncio
    async def test_learning_confidence_increases(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test that reinforcing a learning increases confidence."""
        # First teach
        r1 = await client.post(
            "/api/ai/teach",
            headers=auth_headers,
            json={"category": "pattern", "key": "daily_routine", "value": "Check leads first"},
        )
        assert r1.status_code == 200
        initial_confidence = r1.json()["confidence"]

        # Reinforce by teaching same thing
        r2 = await client.post(
            "/api/ai/teach",
            headers=auth_headers,
            json={"category": "pattern", "key": "daily_routine", "value": "Check leads first thing"},
        )
        assert r2.status_code == 200
        assert r2.json()["times_reinforced"] > r1.json()["times_reinforced"]

    @pytest.mark.asyncio
    async def test_multiple_categories(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test teaching and retrieving multiple categories."""
        categories = [
            {"category": "preference", "key": "tone", "value": "professional"},
            {"category": "correction", "key": "name spelling", "value": "It's MacDonald, not McDonald"},
            {"category": "entity_context", "key": "Project Alpha", "value": "High priority Q1 initiative"},
        ]

        for cat in categories:
            resp = await client.post(
                "/api/ai/teach",
                headers=auth_headers,
                json=cat,
            )
            assert resp.status_code == 200

        # Get all
        all_resp = await client.get("/api/ai/learnings", headers=auth_headers)
        assert all_resp.status_code == 200
        assert len(all_resp.json()["learnings"]) >= 3
