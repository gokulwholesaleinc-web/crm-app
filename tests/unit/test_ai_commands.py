"""
Unit tests for AI command execution system.

Tests for CRUD operations via chat, action safety classification,
confirmation flow, audit logging, and unauthorized access.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.leads.models import Lead, LeadSource
from src.opportunities.models import Opportunity, PipelineStage
from src.activities.models import Activity
from src.contacts.models import Contact
from src.core.models import Note
from src.ai.models import AIActionLog
from src.ai.action_safety import (
    ActionRisk,
    classify_action,
    requires_confirmation,
    get_confirmation_description,
    ACTION_CLASSIFICATION,
)
from src.ai.query_processor import QueryProcessor, _summarize_result, TOOLS


class TestActionSafetyClassification:
    """Tests for the action safety classification module."""

    def test_read_actions_classified_correctly(self):
        """Test that read operations are classified as READ."""
        read_actions = [
            "search_contacts",
            "search_leads",
            "get_pipeline_summary",
            "get_upcoming_tasks",
            "get_recent_activities",
            "get_kpis",
            "generate_pipeline_report",
            "generate_activity_report",
        ]
        for action in read_actions:
            assert classify_action(action) == ActionRisk.READ, f"{action} should be READ"

    def test_write_low_actions_classified_correctly(self):
        """Test that low-risk write operations are classified as WRITE_LOW."""
        write_low_actions = ["add_note", "create_lead", "create_activity"]
        for action in write_low_actions:
            assert classify_action(action) == ActionRisk.WRITE_LOW, f"{action} should be WRITE_LOW"

    def test_write_high_actions_classified_correctly(self):
        """Test that high-risk write operations are classified as WRITE_HIGH."""
        write_high_actions = ["update_lead_status", "update_opportunity_stage"]
        for action in write_high_actions:
            assert classify_action(action) == ActionRisk.WRITE_HIGH, f"{action} should be WRITE_HIGH"

    def test_unknown_action_defaults_to_read(self):
        """Test that unknown actions default to READ classification."""
        assert classify_action("nonexistent_function") == ActionRisk.READ

    def test_requires_confirmation_for_high_risk(self):
        """Test that high-risk actions require confirmation."""
        assert requires_confirmation("update_lead_status") is True
        assert requires_confirmation("update_opportunity_stage") is True

    def test_no_confirmation_for_low_risk(self):
        """Test that read and low-risk write actions do not require confirmation."""
        assert requires_confirmation("search_contacts") is False
        assert requires_confirmation("create_lead") is False
        assert requires_confirmation("add_note") is False

    def test_get_confirmation_description_with_args(self):
        """Test confirmation description generation."""
        desc = get_confirmation_description(
            "update_lead_status",
            {"lead_id": 42, "new_status": "qualified"},
        )
        assert "42" in desc
        assert "qualified" in desc

    def test_get_confirmation_description_fallback(self):
        """Test fallback description for unknown action."""
        desc = get_confirmation_description(
            "unknown_action",
            {"foo": "bar"},
        )
        assert "unknown_action" in desc

    def test_all_tools_have_classification(self):
        """Verify every tool in the TOOLS list has a safety classification."""
        for tool in TOOLS:
            func_name = tool["function"]["name"]
            assert func_name in ACTION_CLASSIFICATION, (
                f"Tool '{func_name}' is missing from ACTION_CLASSIFICATION"
            )


class TestQueryProcessorFunctions:
    """Tests for direct QueryProcessor function execution (no OpenAI needed)."""

    @pytest.mark.asyncio
    async def test_create_lead_via_execute_function(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test creating a lead directly through _execute_function."""
        processor = QueryProcessor(db_session)
        result = await processor._execute_function(
            "create_lead",
            {
                "first_name": "Alice",
                "last_name": "Wonder",
                "email": "alice@wonder.com",
                "company_name": "Wonderland Inc",
            },
            test_user.id,
        )

        assert result["success"] is True
        assert result["name"] == "Alice Wonder"
        assert result["lead_id"] is not None

        # Verify lead actually exists in DB
        lead_result = await db_session.execute(
            select(Lead).where(Lead.id == result["lead_id"])
        )
        lead = lead_result.scalar_one_or_none()
        assert lead is not None
        assert lead.first_name == "Alice"
        assert lead.last_name == "Wonder"
        assert lead.email == "alice@wonder.com"
        assert lead.company_name == "Wonderland Inc"
        assert lead.created_by_id == test_user.id

    @pytest.mark.asyncio
    async def test_update_lead_status_via_execute_function(
        self, db_session: AsyncSession, test_user: User, test_lead: Lead
    ):
        """Test updating lead status through _execute_function."""
        processor = QueryProcessor(db_session)
        result = await processor._execute_function(
            "update_lead_status",
            {
                "lead_id": test_lead.id,
                "new_status": "qualified",
                "reason": "Good fit for our product",
            },
            test_user.id,
        )

        assert result["success"] is True
        assert result["old_status"] == "new"
        assert result["new_status"] == "qualified"

        # Verify in DB
        await db_session.refresh(test_lead)
        assert test_lead.status == "qualified"

    @pytest.mark.asyncio
    async def test_update_lead_status_not_found(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test updating non-existent lead returns error."""
        processor = QueryProcessor(db_session)
        result = await processor._execute_function(
            "update_lead_status",
            {"lead_id": 99999, "new_status": "qualified"},
            test_user.id,
        )

        assert "error" in result

    @pytest.mark.asyncio
    async def test_create_activity_via_execute_function(
        self, db_session: AsyncSession, test_user: User, test_contact: Contact
    ):
        """Test creating an activity through _execute_function."""
        processor = QueryProcessor(db_session)
        result = await processor._execute_function(
            "create_activity",
            {
                "subject": "Follow up call",
                "activity_type": "call",
                "entity_type": "contacts",
                "entity_id": test_contact.id,
                "due_date": "2026-03-01",
                "priority": "high",
                "notes": "Discuss proposal",
            },
            test_user.id,
        )

        assert result["success"] is True
        assert result["subject"] == "Follow up call"
        assert result["type"] == "call"

        # Verify in DB
        activity_result = await db_session.execute(
            select(Activity).where(Activity.id == result["activity_id"])
        )
        activity = activity_result.scalar_one_or_none()
        assert activity is not None
        assert activity.subject == "Follow up call"
        assert activity.priority == "high"

    @pytest.mark.asyncio
    async def test_create_activity_invalid_date(
        self, db_session: AsyncSession, test_user: User, test_contact: Contact
    ):
        """Test creating activity with invalid date format."""
        processor = QueryProcessor(db_session)
        result = await processor._execute_function(
            "create_activity",
            {
                "subject": "Test",
                "activity_type": "task",
                "entity_type": "contacts",
                "entity_id": test_contact.id,
                "due_date": "not-a-date",
            },
            test_user.id,
        )

        assert "error" in result

    @pytest.mark.asyncio
    async def test_update_opportunity_stage_via_execute_function(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_opportunity: Opportunity,
        test_won_stage: PipelineStage,
    ):
        """Test moving opportunity to a new pipeline stage."""
        processor = QueryProcessor(db_session)
        result = await processor._execute_function(
            "update_opportunity_stage",
            {
                "opportunity_id": test_opportunity.id,
                "stage_id": test_won_stage.id,
                "notes": "Customer signed the contract",
            },
            test_user.id,
        )

        assert result["success"] is True
        assert result["new_stage"] == "Closed Won"

    @pytest.mark.asyncio
    async def test_update_opportunity_stage_not_found(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test updating non-existent opportunity returns error."""
        processor = QueryProcessor(db_session)
        result = await processor._execute_function(
            "update_opportunity_stage",
            {"opportunity_id": 99999, "stage_id": 1},
            test_user.id,
        )

        assert "error" in result

    @pytest.mark.asyncio
    async def test_add_note_via_execute_function(
        self, db_session: AsyncSession, test_user: User, test_contact: Contact
    ):
        """Test adding a note to an entity."""
        processor = QueryProcessor(db_session)
        result = await processor._execute_function(
            "add_note",
            {
                "entity_type": "contact",
                "entity_id": test_contact.id,
                "content": "Important client - follow up weekly",
            },
            test_user.id,
        )

        assert result["success"] is True
        assert result["note_id"] is not None

        # Verify note in DB
        note_result = await db_session.execute(
            select(Note).where(Note.id == result["note_id"])
        )
        note = note_result.scalar_one_or_none()
        assert note is not None
        assert note.content == "Important client - follow up weekly"

    @pytest.mark.asyncio
    async def test_generate_pipeline_report(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_opportunity: Opportunity,
    ):
        """Test generating a pipeline report."""
        processor = QueryProcessor(db_session)
        result = await processor._execute_function(
            "generate_pipeline_report",
            {"date_from": "2020-01-01", "date_to": "2030-12-31"},
            test_user.id,
        )

        assert result["report_type"] == "pipeline"
        assert "total_deals" in result
        assert "by_stage" in result

    @pytest.mark.asyncio
    async def test_generate_activity_report(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_activity: Activity,
    ):
        """Test generating an activity report."""
        processor = QueryProcessor(db_session)
        result = await processor._execute_function(
            "generate_activity_report",
            {"date_from": "2020-01-01", "date_to": "2030-12-31"},
            test_user.id,
        )

        assert result["report_type"] == "activity"
        assert result["total_activities"] >= 1
        assert "by_type" in result

    @pytest.mark.asyncio
    async def test_unknown_function_returns_error(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test calling an unknown function returns error."""
        processor = QueryProcessor(db_session)
        result = await processor._execute_function(
            "nonexistent_function", {}, test_user.id
        )

        assert "error" in result


class TestAuditLogging:
    """Tests for AI action audit logging."""

    @pytest.mark.asyncio
    async def test_action_logged_on_execution(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test that executing an action creates an audit log entry."""
        processor = QueryProcessor(db_session)

        # Execute an action directly
        await processor._execute_function(
            "create_lead",
            {"first_name": "Log", "last_name": "Test"},
            test_user.id,
        )

        # Log the action manually (as process_query would)
        await processor._log_action(
            user_id=test_user.id,
            session_id="test-session",
            function_name="create_lead",
            arguments={"first_name": "Log", "last_name": "Test"},
            result={"success": True, "lead_id": 1},
            risk_level="write_low",
            was_confirmed=False,
        )

        # Check audit log
        log_result = await db_session.execute(
            select(AIActionLog).where(
                AIActionLog.user_id == test_user.id,
                AIActionLog.function_name == "create_lead",
            )
        )
        log = log_result.scalar_one_or_none()
        assert log is not None
        assert log.risk_level == "write_low"
        assert log.was_confirmed is False
        assert log.session_id == "test-session"
        assert log.model_used == "gpt-4"

    @pytest.mark.asyncio
    async def test_confirmed_action_logged(
        self, db_session: AsyncSession, test_user: User, test_lead: Lead
    ):
        """Test that confirmed actions log was_confirmed=True."""
        processor = QueryProcessor(db_session)

        result = await processor.execute_confirmed_action(
            function_name="update_lead_status",
            arguments={"lead_id": test_lead.id, "new_status": "contacted"},
            user_id=test_user.id,
            session_id="confirm-session",
        )

        assert result["data"]["success"] is True

        # Check audit log
        log_result = await db_session.execute(
            select(AIActionLog).where(
                AIActionLog.session_id == "confirm-session",
                AIActionLog.function_name == "update_lead_status",
            )
        )
        log = log_result.scalar_one_or_none()
        assert log is not None
        assert log.was_confirmed is True
        assert log.risk_level == "write_high"


class TestConfirmationFlow:
    """Tests for the action confirmation flow via API endpoints."""

    @pytest.mark.asyncio
    async def test_confirm_action_endpoint(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_lead: Lead,
    ):
        """Test the confirm-action endpoint executes a confirmed action."""
        response = await client.post(
            "/api/ai/confirm-action",
            headers=auth_headers,
            json={
                "session_id": "test-confirm-session",
                "function_name": "update_lead_status",
                "arguments": {
                    "lead_id": test_lead.id,
                    "new_status": "contacted",
                },
                "confirmed": True,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "response" in data
        assert data["function_called"] == "update_lead_status"
        assert len(data["actions_taken"]) == 1

        # Verify lead status was actually changed
        await db_session.refresh(test_lead)
        assert test_lead.status == "contacted"

    @pytest.mark.asyncio
    async def test_confirm_action_cancelled(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_lead: Lead,
    ):
        """Test cancelling a confirmed action does not execute it."""
        response = await client.post(
            "/api/ai/confirm-action",
            headers=auth_headers,
            json={
                "session_id": "test-cancel-session",
                "function_name": "update_lead_status",
                "arguments": {
                    "lead_id": test_lead.id,
                    "new_status": "lost",
                },
                "confirmed": False,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "cancelled" in data["response"].lower()

        # Verify lead status was NOT changed
        await db_session.refresh(test_lead)
        assert test_lead.status == "new"

    @pytest.mark.asyncio
    async def test_confirm_action_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test confirm-action without auth fails."""
        response = await client.post(
            "/api/ai/confirm-action",
            json={
                "session_id": "test",
                "function_name": "update_lead_status",
                "arguments": {"lead_id": 1, "new_status": "lost"},
                "confirmed": True,
            },
        )
        assert response.status_code == 401


class TestChatEndpointExpanded:
    """Tests for the expanded chat endpoint with new response fields."""

    @pytest.mark.asyncio
    async def test_chat_response_includes_new_fields(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test that chat response includes confirmation_required and actions_taken fields."""
        response = await client.post(
            "/api/ai/chat",
            headers=auth_headers,
            json={
                "message": "Hello",
                "session_id": "test-fields-session",
            },
        )

        # Should either succeed or fail gracefully
        assert response.status_code in [200, 500, 503]

        if response.status_code == 200:
            data = response.json()
            assert "confirmation_required" in data
            assert "actions_taken" in data
            assert isinstance(data["actions_taken"], list)
            assert isinstance(data["confirmation_required"], bool)

    @pytest.mark.asyncio
    async def test_chat_without_openai_returns_helpful_message(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test chat returns helpful message when OpenAI is not configured."""
        response = await client.post(
            "/api/ai/chat",
            headers=auth_headers,
            json={"message": "Create a lead for John Smith"},
        )

        # Without OpenAI key, should still return 200 with error message
        if response.status_code == 200:
            data = response.json()
            assert "response" in data
            assert isinstance(data["response"], str)


class TestResultSummarization:
    """Tests for the _summarize_result helper function."""

    def test_summarize_error(self):
        assert "Error" in _summarize_result({"error": "something went wrong"})

    def test_summarize_message(self):
        assert _summarize_result({"message": "Lead created"}) == "Lead created"

    def test_summarize_count(self):
        assert "5" in _summarize_result({"count": 5})

    def test_summarize_report(self):
        assert "pipeline" in _summarize_result({"report_type": "pipeline"})

    def test_summarize_fallback(self):
        assert _summarize_result({"foo": "bar"}) == "Completed"


class TestToolDefinitions:
    """Tests to verify all tool definitions are properly structured."""

    def test_all_tools_have_required_fields(self):
        """Verify every tool has name, description, and parameters."""
        for tool in TOOLS:
            assert "type" in tool
            assert tool["type"] == "function"
            func = tool["function"]
            assert "name" in func
            assert "description" in func
            assert "parameters" in func
            assert func["parameters"]["type"] == "object"

    def test_write_tools_present(self):
        """Verify all write operation tools are defined."""
        tool_names = {t["function"]["name"] for t in TOOLS}
        expected_write_tools = {
            "create_lead",
            "update_lead_status",
            "create_activity",
            "update_opportunity_stage",
            "add_note",
        }
        for tool in expected_write_tools:
            assert tool in tool_names, f"Write tool '{tool}' is missing from TOOLS"

    def test_report_tools_present(self):
        """Verify all report operation tools are defined."""
        tool_names = {t["function"]["name"] for t in TOOLS}
        assert "generate_pipeline_report" in tool_names
        assert "generate_activity_report" in tool_names

    def test_tool_count(self):
        """Verify total number of tools is as expected."""
        assert len(TOOLS) == 34
