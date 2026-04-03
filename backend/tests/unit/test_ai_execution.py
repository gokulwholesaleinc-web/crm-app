"""
Unit tests for AI autonomous execution capabilities.

Tests for pipeline intelligence, execution tools, action safety
classifications, quote/proposal/payment creation, follow-up sequences,
and campaign triggers.
"""

import pytest
from datetime import date, datetime, timedelta, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.leads.models import Lead, LeadSource
from src.opportunities.models import Opportunity, PipelineStage
from src.activities.models import Activity
from src.contacts.models import Contact
from src.companies.models import Company
from src.quotes.models import Quote
from src.proposals.models import Proposal
from src.campaigns.models import Campaign
from src.ai.action_safety import (
    ActionRisk,
    classify_action,
    requires_confirmation,
    get_confirmation_description,
    ACTION_CLASSIFICATION,
)
from src.ai.query_processor import QueryProcessor, TOOLS


class TestNewActionSafetyClassification:
    """Tests for safety classification of new execution tools."""

    def test_pipeline_intelligence_tools_are_safe(self):
        """Analysis tools should be READ (no confirmation needed)."""
        safe_tools = [
            "analyze_pipeline",
            "suggest_improvements",
            "get_stale_deals",
            "get_follow_up_priorities",
        ]
        for tool in safe_tools:
            assert classify_action(tool) == ActionRisk.READ, f"{tool} should be READ"
            assert requires_confirmation(tool) is False, f"{tool} should not require confirmation"

    def test_execution_tools_need_confirmation(self):
        """Send/create execution tools should require confirmation."""
        confirmation_tools = [
            "create_and_send_quote",
            "resend_quote",
            "create_and_send_proposal",
            "resend_proposal",
            "create_payment_link",
            "send_invoice",
            "send_email_to_contact",
            "schedule_follow_up_sequence",
            "send_campaign_to_segment",
        ]
        for tool in confirmation_tools:
            assert classify_action(tool) == ActionRisk.WRITE_HIGH, f"{tool} should be WRITE_HIGH"
            assert requires_confirmation(tool) is True, f"{tool} should require confirmation"

    def test_all_new_tools_have_classification(self):
        """Verify every tool in TOOLS list has a safety classification."""
        for tool in TOOLS:
            func_name = tool["function"]["name"]
            assert func_name in ACTION_CLASSIFICATION, (
                f"Tool '{func_name}' is missing from ACTION_CLASSIFICATION"
            )

    def test_confirmation_descriptions_for_new_tools(self):
        """Test confirmation descriptions render properly for new tools."""
        desc = get_confirmation_description(
            "create_and_send_quote",
            {"title": "Web Dev", "contact_id": 5},
        )
        assert "Web Dev" in desc
        assert "5" in desc

        desc = get_confirmation_description(
            "send_email_to_contact",
            {"contact_id": 3, "subject": "Follow up"},
        )
        assert "3" in desc
        assert "Follow up" in desc

        desc = get_confirmation_description(
            "create_payment_link",
            {"amount": 1500, "currency": "USD"},
        )
        assert "1500" in desc
        assert "USD" in desc


class TestNewToolDefinitions:
    """Tests for new tool definitions in TOOLS list."""

    def test_new_tools_present(self):
        """Verify all new tools are defined in the TOOLS list."""
        tool_names = {t["function"]["name"] for t in TOOLS}
        expected_new_tools = {
            "analyze_pipeline",
            "suggest_improvements",
            "get_stale_deals",
            "get_follow_up_priorities",
            "create_and_send_quote",
            "resend_quote",
            "create_and_send_proposal",
            "resend_proposal",
            "create_payment_link",
            "send_invoice",
            "send_email_to_contact",
            "schedule_follow_up_sequence",
            "send_campaign_to_segment",
        }
        for tool in expected_new_tools:
            assert tool in tool_names, f"New tool '{tool}' is missing from TOOLS"

    def test_new_tools_have_valid_structure(self):
        """Verify new tools have proper name, description, and parameters."""
        new_tool_names = {
            "analyze_pipeline", "suggest_improvements", "get_stale_deals",
            "get_follow_up_priorities", "create_and_send_quote", "resend_quote",
            "create_and_send_proposal", "resend_proposal", "create_payment_link",
            "send_invoice", "send_email_to_contact", "schedule_follow_up_sequence",
            "send_campaign_to_segment",
        }
        for tool in TOOLS:
            func = tool["function"]
            if func["name"] in new_tool_names:
                assert "description" in func, f"{func['name']} missing description"
                assert len(func["description"]) > 10, f"{func['name']} description too short"
                assert "parameters" in func, f"{func['name']} missing parameters"
                assert func["parameters"]["type"] == "object"

    def test_total_tool_count(self):
        """Verify total tool count after adding new tools."""
        # 21 original + 13 new = 34
        assert len(TOOLS) == 34


class TestAnalyzePipeline:
    """Tests for the analyze_pipeline tool."""

    @pytest.mark.asyncio
    async def test_analyze_pipeline_returns_structured_data(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_opportunity: Opportunity,
    ):
        """Test that pipeline analysis returns all expected fields."""
        processor = QueryProcessor(db_session)
        result = await processor._execute_function(
            "analyze_pipeline", {"days": 30}, test_user.id
        )

        assert "total_deals" in result
        assert "open_deals" in result
        assert "total_pipeline_value" in result
        assert "weighted_forecast" in result
        assert "by_stage" in result
        assert "recommendations" in result
        assert "deals_at_risk" in result
        assert "upcoming_closes_14d" in result
        assert "current_period_won_value" in result
        assert "previous_period_won_value" in result
        assert isinstance(result["by_stage"], list)
        assert isinstance(result["recommendations"], list)

    @pytest.mark.asyncio
    async def test_analyze_pipeline_default_days(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_opportunity: Opportunity,
    ):
        """Test pipeline analysis with default 30 days."""
        processor = QueryProcessor(db_session)
        result = await processor._execute_function(
            "analyze_pipeline", {}, test_user.id
        )

        assert result["analysis_period_days"] == 30
        assert result["total_deals"] >= 1

    @pytest.mark.asyncio
    async def test_analyze_pipeline_counts_deals_correctly(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_opportunity: Opportunity,
    ):
        """Test that pipeline analysis counts the test opportunity."""
        processor = QueryProcessor(db_session)
        result = await processor._execute_function(
            "analyze_pipeline", {}, test_user.id
        )

        assert result["total_pipeline_value"] >= 50000.0
        assert result["open_deals"] >= 1


class TestSuggestImprovements:
    """Tests for the suggest_improvements tool."""

    @pytest.mark.asyncio
    async def test_suggest_improvements_for_opportunity(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_opportunity: Opportunity,
    ):
        """Test improvement suggestions for a specific opportunity."""
        processor = QueryProcessor(db_session)
        result = await processor._execute_function(
            "suggest_improvements",
            {"opportunity_id": test_opportunity.id},
            test_user.id,
        )

        assert "opportunity_id" in result
        assert "name" in result
        assert "risk_factors" in result
        assert "suggested_actions" in result
        assert isinstance(result["risk_factors"], list)
        assert isinstance(result["suggested_actions"], list)
        assert len(result["suggested_actions"]) > 0

    @pytest.mark.asyncio
    async def test_suggest_improvements_not_found(
        self,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test improvement suggestions for non-existent opportunity."""
        processor = QueryProcessor(db_session)
        result = await processor._execute_function(
            "suggest_improvements", {"opportunity_id": 99999}, test_user.id
        )

        assert "error" in result

    @pytest.mark.asyncio
    async def test_suggest_improvements_pipeline_wide(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_opportunity: Opportunity,
    ):
        """Test pipeline-wide improvement suggestions."""
        processor = QueryProcessor(db_session)
        result = await processor._execute_function(
            "suggest_improvements", {}, test_user.id
        )

        assert "pipeline_summary" in result
        assert "improvement_suggestions" in result
        assert isinstance(result["improvement_suggestions"], list)
        assert len(result["improvement_suggestions"]) > 0


class TestGetStaleDeals:
    """Tests for the get_stale_deals tool."""

    @pytest.mark.asyncio
    async def test_get_stale_deals_finds_inactive_opportunities(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_opportunity: Opportunity,
    ):
        """Test finding stale deals (no recent activity)."""
        processor = QueryProcessor(db_session)
        result = await processor._execute_function(
            "get_stale_deals", {"days_idle": 7}, test_user.id
        )

        assert "stale_deals_count" in result
        assert "deals" in result
        assert "days_idle_threshold" in result
        assert result["days_idle_threshold"] == 7
        assert isinstance(result["deals"], list)
        # Our test opportunity has no activities, so it should be stale
        assert result["stale_deals_count"] >= 1

    @pytest.mark.asyncio
    async def test_get_stale_deals_default_days(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_opportunity: Opportunity,
    ):
        """Test stale deals with default days parameter."""
        processor = QueryProcessor(db_session)
        result = await processor._execute_function(
            "get_stale_deals", {}, test_user.id
        )

        assert result["days_idle_threshold"] == 7

    @pytest.mark.asyncio
    async def test_stale_deals_include_suggested_actions(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_opportunity: Opportunity,
    ):
        """Test that stale deals include suggested actions."""
        processor = QueryProcessor(db_session)
        result = await processor._execute_function(
            "get_stale_deals", {}, test_user.id
        )

        for deal in result["deals"]:
            assert "suggested_action" in deal
            assert "name" in deal
            assert "amount" in deal


class TestGetFollowUpPriorities:
    """Tests for the get_follow_up_priorities tool."""

    @pytest.mark.asyncio
    async def test_get_follow_up_priorities_returns_ranked_list(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_opportunity: Opportunity,
    ):
        """Test follow-up priorities returns ranked contacts."""
        processor = QueryProcessor(db_session)
        result = await processor._execute_function(
            "get_follow_up_priorities", {}, test_user.id
        )

        assert "count" in result
        assert "priorities" in result
        assert isinstance(result["priorities"], list)
        assert result["count"] >= 1

        for priority in result["priorities"]:
            assert "opportunity_id" in priority
            assert "urgency_score" in priority
            assert "reasons" in priority
            assert "suggested_action" in priority

    @pytest.mark.asyncio
    async def test_follow_up_priorities_sorted_by_urgency(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_opportunity: Opportunity,
    ):
        """Test that priorities are sorted by urgency score descending."""
        processor = QueryProcessor(db_session)
        result = await processor._execute_function(
            "get_follow_up_priorities", {}, test_user.id
        )

        priorities = result["priorities"]
        for i in range(len(priorities) - 1):
            assert priorities[i]["urgency_score"] >= priorities[i + 1]["urgency_score"]


class TestCreateAndSendQuote:
    """Tests for the create_and_send_quote tool."""

    @pytest.mark.asyncio
    async def test_create_quote_with_line_items(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_contact: Contact,
        test_opportunity: Opportunity,
    ):
        """Test creating a quote with line items returns public URL."""
        processor = QueryProcessor(db_session)
        result = await processor._execute_function(
            "create_and_send_quote",
            {
                "title": "Web Development Project",
                "contact_id": test_contact.id,
                "opportunity_id": test_opportunity.id,
                "line_items": [
                    {"description": "Frontend Development", "quantity": 1, "unit_price": 5000},
                    {"description": "Backend Development", "quantity": 1, "unit_price": 8000},
                ],
                "valid_days": 30,
                "send_immediately": False,
            },
            test_user.id,
        )

        assert result["success"] is True
        assert result["quote_id"] is not None
        assert result["quote_number"] is not None
        assert result["total"] == 13000.0
        assert "public_url" in result
        assert f"/quotes/public/{result['quote_number']}" in result["public_url"]

        # Verify quote in DB
        quote_result = await db_session.execute(
            select(Quote).where(Quote.id == result["quote_id"])
        )
        quote = quote_result.scalar_one_or_none()
        assert quote is not None
        assert quote.title == "Web Development Project"
        assert quote.contact_id == test_contact.id

    @pytest.mark.asyncio
    async def test_create_quote_without_line_items(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_contact: Contact,
    ):
        """Test creating a quote without line items still returns public URL."""
        processor = QueryProcessor(db_session)
        result = await processor._execute_function(
            "create_and_send_quote",
            {
                "title": "Consulting Services",
                "contact_id": test_contact.id,
            },
            test_user.id,
        )

        assert result["success"] is True
        assert result["quote_id"] is not None
        assert "public_url" in result

    @pytest.mark.asyncio
    async def test_create_and_send_quote_immediately(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_contact: Contact,
    ):
        """Test creating a quote and sending immediately sends email with public link."""
        processor = QueryProcessor(db_session)
        result = await processor._execute_function(
            "create_and_send_quote",
            {
                "title": "Urgent Quote",
                "contact_id": test_contact.id,
                "line_items": [
                    {"description": "Service", "quantity": 1, "unit_price": 2000},
                ],
                "send_immediately": True,
            },
            test_user.id,
        )

        assert result["success"] is True
        assert result["email_sent"] is True
        assert result["status"] == "sent"
        assert "public link" in result["message"]

        # Verify quote status transitioned to sent in DB
        quote_result = await db_session.execute(
            select(Quote).where(Quote.id == result["quote_id"])
        )
        quote = quote_result.scalar_one_or_none()
        assert quote is not None
        assert quote.status == "sent"
        assert quote.sent_at is not None


class TestCreatePaymentLink:
    """Tests for the create_payment_link tool."""

    @pytest.mark.asyncio
    async def test_create_payment_link_no_stripe(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_contact: Contact,
    ):
        """Test payment link creation fails gracefully without Stripe."""
        processor = QueryProcessor(db_session)
        result = await processor._execute_function(
            "create_payment_link",
            {
                "amount": 1500.00,
                "currency": "USD",
                "contact_id": test_contact.id,
                "description": "Consulting fee",
            },
            test_user.id,
        )

        # Without Stripe configured, should return an error
        assert "error" in result
        assert "Stripe" in result["error"]


class TestCreateAndSendProposal:
    """Tests for the create_and_send_proposal tool."""

    @pytest.mark.asyncio
    async def test_create_proposal_for_opportunity(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_opportunity: Opportunity,
    ):
        """Test creating a proposal for an opportunity."""
        processor = QueryProcessor(db_session)
        result = await processor._execute_function(
            "create_and_send_proposal",
            {
                "opportunity_id": test_opportunity.id,
                "send_immediately": False,
            },
            test_user.id,
        )

        assert result["success"] is True
        assert result["proposal_id"] is not None
        assert result["proposal_number"] is not None
        assert "Test Deal" in result["title"]

        # Verify proposal in DB
        proposal_result = await db_session.execute(
            select(Proposal).where(Proposal.id == result["proposal_id"])
        )
        proposal = proposal_result.scalar_one_or_none()
        assert proposal is not None
        assert proposal.opportunity_id == test_opportunity.id

    @pytest.mark.asyncio
    async def test_create_proposal_not_found(
        self,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test creating proposal for non-existent opportunity."""
        processor = QueryProcessor(db_session)
        result = await processor._execute_function(
            "create_and_send_proposal",
            {"opportunity_id": 99999},
            test_user.id,
        )

        assert "error" in result


class TestScheduleFollowUpSequence:
    """Tests for the schedule_follow_up_sequence tool."""

    @pytest.mark.asyncio
    async def test_schedule_follow_up_creates_activities(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_contact: Contact,
    ):
        """Test that scheduling a follow-up sequence creates activities."""
        processor = QueryProcessor(db_session)
        result = await processor._execute_function(
            "schedule_follow_up_sequence",
            {
                "entity_type": "contacts",
                "entity_id": test_contact.id,
                "steps": [
                    {"delay_days": 1, "activity_type": "email", "subject": "Introduction email", "description": "Send intro"},
                    {"delay_days": 3, "activity_type": "call", "subject": "Follow-up call", "description": "Call to discuss"},
                    {"delay_days": 7, "activity_type": "meeting", "subject": "Demo meeting", "description": "Present solution"},
                ],
            },
            test_user.id,
        )

        assert result["success"] is True
        assert result["activities_created"] == 3
        assert len(result["activities"]) == 3

        # Verify activities in DB
        for act_info in result["activities"]:
            act_result = await db_session.execute(
                select(Activity).where(Activity.id == act_info["activity_id"])
            )
            activity = act_result.scalar_one_or_none()
            assert activity is not None
            assert activity.entity_type == "contacts"
            assert activity.entity_id == test_contact.id

    @pytest.mark.asyncio
    async def test_schedule_follow_up_empty_steps(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_contact: Contact,
    ):
        """Test scheduling with empty steps returns error."""
        processor = QueryProcessor(db_session)
        result = await processor._execute_function(
            "schedule_follow_up_sequence",
            {
                "entity_type": "contacts",
                "entity_id": test_contact.id,
                "steps": [],
            },
            test_user.id,
        )

        assert "error" in result


class TestSendEmailToContact:
    """Tests for the send_email_to_contact tool."""

    @pytest.mark.asyncio
    async def test_send_email_contact_not_found(
        self,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test sending email to non-existent contact."""
        processor = QueryProcessor(db_session)
        result = await processor._execute_function(
            "send_email_to_contact",
            {
                "contact_id": 99999,
                "subject": "Test",
                "body": "Hello",
            },
            test_user.id,
        )

        assert "error" in result

    @pytest.mark.asyncio
    async def test_send_email_to_contact_success(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_contact: Contact,
    ):
        """Test sending email to a contact (SMTP will fail, but queue entry is created)."""
        processor = QueryProcessor(db_session)
        result = await processor._execute_function(
            "send_email_to_contact",
            {
                "contact_id": test_contact.id,
                "subject": "Follow-up on our meeting",
                "body": "<p>Thank you for your time.</p>",
                "use_branded_template": False,
            },
            test_user.id,
        )

        # Email queueing should succeed even if SMTP fails
        assert result["success"] is True
        assert test_contact.full_name in result["message"]


class TestSendCampaignToSegment:
    """Tests for the send_campaign_to_segment tool."""

    @pytest.mark.asyncio
    async def test_send_campaign_not_found(
        self,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test sending non-existent campaign."""
        processor = QueryProcessor(db_session)
        result = await processor._execute_function(
            "send_campaign_to_segment",
            {"campaign_id": 99999},
            test_user.id,
        )

        assert "error" in result

    @pytest.mark.asyncio
    async def test_send_campaign_starts_execution(
        self,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test triggering campaign execution updates status."""
        campaign = Campaign(
            name="Test Campaign",
            campaign_type="email",
            status="draft",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(campaign)
        await db_session.flush()
        await db_session.refresh(campaign)

        processor = QueryProcessor(db_session)
        result = await processor._execute_function(
            "send_campaign_to_segment",
            {"campaign_id": campaign.id},
            test_user.id,
        )

        assert result["success"] is True
        assert result["status"] == "in_progress"

        # Verify in DB
        await db_session.refresh(campaign)
        assert campaign.status == "in_progress"


class TestResendQuote:
    """Tests for the resend_quote tool."""

    @pytest.mark.asyncio
    async def test_resend_quote_not_found(
        self,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test resending non-existent quote."""
        processor = QueryProcessor(db_session)
        result = await processor._execute_function(
            "resend_quote", {"quote_id": 99999}, test_user.id
        )

        assert "error" in result


class TestResendProposal:
    """Tests for the resend_proposal tool."""

    @pytest.mark.asyncio
    async def test_resend_proposal_not_found(
        self,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test resending non-existent proposal."""
        processor = QueryProcessor(db_session)
        result = await processor._execute_function(
            "resend_proposal", {"proposal_id": 99999}, test_user.id
        )

        assert "error" in result


class TestSendInvoice:
    """Tests for the send_invoice tool."""

    @pytest.mark.asyncio
    async def test_send_invoice_not_found(
        self,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test sending invoice for non-existent payment."""
        processor = QueryProcessor(db_session)
        result = await processor._execute_function(
            "send_invoice", {"payment_id": 99999}, test_user.id
        )

        assert "error" in result


class TestSystemPromptUpdated:
    """Tests for the updated system prompt."""

    def test_system_prompt_mentions_autonomous(self):
        """Verify system prompt promotes autonomous behavior."""
        from src.ai.query_processor import SYSTEM_PROMPT_BASE
        assert "autonomous" in SYSTEM_PROMPT_BASE.lower()
        assert "take action" in SYSTEM_PROMPT_BASE.lower()
        assert "proactively" in SYSTEM_PROMPT_BASE.lower()
