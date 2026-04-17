"""Natural language query processor for AI assistant — thin orchestrator."""

import logging
import uuid
from typing import Dict, Any, List, Optional

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.ai.conversation_manager import AIConversationManager
from src.ai.tool_executor import AIToolExecutor, _summarize_result
from src.ai.query_tools import CRMQueryTools
from src.ai.action_tools import CRMActionTools
from src.ai.analytics_tools import CRMAnalyticsTools
from src.ai.action_safety import classify_action, ActionRisk
from src.ai.learning_service import AILearningService

logger = logging.getLogger(__name__)

# Re-export for backward compatibility
__all__ = ["QueryProcessor", "_summarize_result", "TOOLS", "SYSTEM_PROMPT_BASE"]

# Tool definitions for the OpenAI tools API
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_contacts",
            "description": "Search for contacts by name, email, company, or other criteria",
            "parameters": {
                "type": "object",
                "properties": {
                    "search_term": {"type": "string", "description": "Search term for name or email"},
                    "company": {"type": "string", "description": "Company name filter"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_leads",
            "description": "Search for leads by name, company, status, or score",
            "parameters": {
                "type": "object",
                "properties": {
                    "search_term": {"type": "string"},
                    "status": {"type": "string", "enum": ["new", "contacted", "qualified", "unqualified", "converted", "lost"]},
                    "min_score": {"type": "integer"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_pipeline_summary",
            "description": "Get summary of sales pipeline including total value and deals by stage",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_upcoming_tasks",
            "description": "Get upcoming tasks and activities",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "Number of days ahead to look"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_recent_activities",
            "description": "Get recent activities for an entity or the user",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_type": {"type": "string"},
                    "entity_id": {"type": "integer"},
                    "limit": {"type": "integer"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_kpis",
            "description": "Get key performance indicators and metrics",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    # Write operations
    {
        "type": "function",
        "function": {
            "name": "create_lead",
            "description": "Create a new lead in the CRM system",
            "parameters": {
                "type": "object",
                "properties": {
                    "first_name": {"type": "string", "description": "Lead's first name"},
                    "last_name": {"type": "string", "description": "Lead's last name"},
                    "email": {"type": "string", "description": "Lead's email address"},
                    "company_name": {"type": "string", "description": "Lead's company name"},
                    "source": {"type": "string", "description": "How the lead was sourced"},
                    "notes": {"type": "string", "description": "Additional notes about the lead"},
                },
                "required": ["first_name", "last_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_lead_status",
            "description": "Change the status of an existing lead",
            "parameters": {
                "type": "object",
                "properties": {
                    "lead_id": {"type": "integer", "description": "ID of the lead to update"},
                    "new_status": {
                        "type": "string",
                        "enum": ["new", "contacted", "qualified", "unqualified", "converted", "lost"],
                        "description": "New status for the lead",
                    },
                    "reason": {"type": "string", "description": "Reason for status change"},
                },
                "required": ["lead_id", "new_status"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_activity",
            "description": "Schedule a task, call, meeting, or other activity",
            "parameters": {
                "type": "object",
                "properties": {
                    "subject": {"type": "string", "description": "Subject/title of the activity"},
                    "activity_type": {
                        "type": "string",
                        "enum": ["call", "email", "meeting", "task", "note"],
                        "description": "Type of activity",
                    },
                    "entity_type": {
                        "type": "string",
                        "description": "Entity type to link to (contacts, leads, opportunities, companies)",
                    },
                    "entity_id": {"type": "integer", "description": "ID of the entity to link to"},
                    "due_date": {"type": "string", "description": "Due date in YYYY-MM-DD format"},
                    "priority": {
                        "type": "string",
                        "enum": ["low", "normal", "high", "urgent"],
                        "description": "Priority level",
                    },
                    "notes": {"type": "string", "description": "Description or notes for the activity"},
                },
                "required": ["subject", "activity_type", "entity_type", "entity_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_opportunity_stage",
            "description": "Move an opportunity to a different pipeline stage",
            "parameters": {
                "type": "object",
                "properties": {
                    "opportunity_id": {"type": "integer", "description": "ID of the opportunity"},
                    "stage_id": {"type": "integer", "description": "ID of the target pipeline stage"},
                    "notes": {"type": "string", "description": "Notes about the stage change"},
                },
                "required": ["opportunity_id", "stage_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_note",
            "description": "Add a note to any entity (contact, lead, opportunity, company)",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_type": {
                        "type": "string",
                        "description": "Entity type (contact, lead, opportunity, company)",
                    },
                    "entity_id": {"type": "integer", "description": "ID of the entity"},
                    "content": {"type": "string", "description": "Note content"},
                },
                "required": ["entity_type", "entity_id", "content"],
            },
        },
    },
    # Report operations
    {
        "type": "function",
        "function": {
            "name": "generate_pipeline_report",
            "description": "Generate a detailed pipeline report for a date range",
            "parameters": {
                "type": "object",
                "properties": {
                    "date_from": {"type": "string", "description": "Start date in YYYY-MM-DD format"},
                    "date_to": {"type": "string", "description": "End date in YYYY-MM-DD format"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_activity_report",
            "description": "Generate an activity summary report for a user over a date range",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "integer", "description": "User ID to report on (omit for current user)"},
                    "date_from": {"type": "string", "description": "Start date in YYYY-MM-DD format"},
                    "date_to": {"type": "string", "description": "End date in YYYY-MM-DD format"},
                },
            },
        },
    },
    # Extended tools for quotes, proposals, payments, campaigns
    {"type": "function", "function": {"name": "search_quotes", "description": "Search quotes by status, contact, or company", "parameters": {"type": "object", "properties": {"status": {"type": "string", "enum": ["draft", "sent", "accepted", "rejected", "expired"]}, "search_term": {"type": "string"}, "limit": {"type": "integer"}}}}},
    {"type": "function", "function": {"name": "get_quote_details", "description": "Get full details of a specific quote including line items", "parameters": {"type": "object", "properties": {"quote_id": {"type": "integer", "description": "ID of the quote"}}, "required": ["quote_id"]}}},
    {"type": "function", "function": {"name": "search_proposals", "description": "Search proposals by status or title", "parameters": {"type": "object", "properties": {"status": {"type": "string"}, "search_term": {"type": "string"}, "limit": {"type": "integer"}}}}},
    {"type": "function", "function": {"name": "get_payment_summary", "description": "Get summary of payments including totals by status", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "list_recent_payments", "description": "List recent payments with optional status filter", "parameters": {"type": "object", "properties": {"status": {"type": "string"}, "limit": {"type": "integer"}}}}},
    {"type": "function", "function": {"name": "get_campaign_stats", "description": "Get campaign statistics and performance data", "parameters": {"type": "object", "properties": {"campaign_id": {"type": "integer"}}}}},
    {"type": "function", "function": {"name": "remember_preference", "description": "Remember a user preference or important context for future interactions", "parameters": {"type": "object", "properties": {"category": {"type": "string", "description": "Category: preference, entity_context, or pattern"}, "key": {"type": "string", "description": "What to remember"}, "value": {"type": "string", "description": "The preference or context value"}}, "required": ["category", "key", "value"]}}},
    {"type": "function", "function": {"name": "get_deal_coaching", "description": "Get AI coaching tips for a specific opportunity", "parameters": {"type": "object", "properties": {"opportunity_id": {"type": "integer", "description": "ID of the opportunity"}}, "required": ["opportunity_id"]}}},
    # Pipeline intelligence tools
    {"type": "function", "function": {"name": "analyze_pipeline", "description": "Analyze the sales pipeline and provide detailed insights including total value, deals by stage, win rate, stale deals, revenue forecast, and comparison to previous period", "parameters": {"type": "object", "properties": {"days": {"type": "integer", "description": "Analysis period in days (default 30)"}}}}},
    {"type": "function", "function": {"name": "suggest_improvements", "description": "Propose an improvement plan for a specific deal or the whole pipeline. Returns next steps, risk factors, bottlenecks, and optimization suggestions", "parameters": {"type": "object", "properties": {"opportunity_id": {"type": "integer", "description": "ID of a specific opportunity (omit for full pipeline)"}}}}},
    {"type": "function", "function": {"name": "get_stale_deals", "description": "Find opportunities with no recent activity that need attention", "parameters": {"type": "object", "properties": {"days_idle": {"type": "integer", "description": "Number of days with no activity to consider stale (default 7)"}}}}},
    {"type": "function", "function": {"name": "get_follow_up_priorities", "description": "Rank contacts and leads by follow-up urgency based on deal value, days since last contact, stage, and close date proximity", "parameters": {"type": "object", "properties": {}}}},
    # Quote execution tools
    {"type": "function", "function": {"name": "create_and_send_quote", "description": "Create a quote with line items and optionally send it to the client", "parameters": {"type": "object", "properties": {"title": {"type": "string", "description": "Quote title"}, "contact_id": {"type": "integer", "description": "Contact to send to"}, "opportunity_id": {"type": "integer", "description": "Associated opportunity"}, "line_items": {"type": "array", "items": {"type": "object", "properties": {"description": {"type": "string"}, "quantity": {"type": "number"}, "unit_price": {"type": "number"}}}, "description": "Line items"}, "valid_days": {"type": "integer", "description": "Days until expiry (default 30)"}, "send_immediately": {"type": "boolean", "description": "Send to client immediately"}}, "required": ["title", "contact_id"]}}},
    {"type": "function", "function": {"name": "resend_quote", "description": "Resend an existing quote to the client", "parameters": {"type": "object", "properties": {"quote_id": {"type": "integer", "description": "ID of the quote to resend"}}, "required": ["quote_id"]}}},
    # Proposal execution tools
    {"type": "function", "function": {"name": "create_and_send_proposal", "description": "Generate an AI proposal for an opportunity and optionally send it to the client", "parameters": {"type": "object", "properties": {"opportunity_id": {"type": "integer", "description": "Opportunity to create proposal for"}, "template_id": {"type": "integer", "description": "Optional proposal template ID"}, "send_immediately": {"type": "boolean", "description": "Send to client immediately"}}, "required": ["opportunity_id"]}}},
    {"type": "function", "function": {"name": "resend_proposal", "description": "Resend an existing proposal to the client", "parameters": {"type": "object", "properties": {"proposal_id": {"type": "integer", "description": "ID of the proposal to resend"}}, "required": ["proposal_id"]}}},
    # Payment execution tools
    {"type": "function", "function": {"name": "create_payment_link", "description": "Create a Stripe checkout link and optionally email it to the contact", "parameters": {"type": "object", "properties": {"amount": {"type": "number", "description": "Payment amount"}, "currency": {"type": "string", "description": "Currency code (default USD)"}, "contact_id": {"type": "integer", "description": "Contact to email link to"}, "quote_id": {"type": "integer", "description": "Associated quote"}, "description": {"type": "string", "description": "Payment description"}}, "required": ["amount"]}}},
    {"type": "function", "function": {"name": "send_invoice", "description": "Generate and send an invoice for a completed payment", "parameters": {"type": "object", "properties": {"payment_id": {"type": "integer", "description": "ID of the payment"}}, "required": ["payment_id"]}}},
    # Communication tools
    {"type": "function", "function": {"name": "send_email_to_contact", "description": "Send a branded email to a contact", "parameters": {"type": "object", "properties": {"contact_id": {"type": "integer", "description": "Contact to email"}, "subject": {"type": "string", "description": "Email subject"}, "body": {"type": "string", "description": "Email body (HTML supported)"}, "use_branded_template": {"type": "boolean", "description": "Wrap in branded template (default true)"}}, "required": ["contact_id", "subject", "body"]}}},
    {"type": "function", "function": {"name": "schedule_follow_up_sequence", "description": "Create a multi-step follow-up sequence as scheduled activities", "parameters": {"type": "object", "properties": {"entity_type": {"type": "string", "description": "Entity type (contacts, leads, opportunities)"}, "entity_id": {"type": "integer", "description": "Entity ID"}, "steps": {"type": "array", "items": {"type": "object", "properties": {"delay_days": {"type": "integer"}, "activity_type": {"type": "string"}, "subject": {"type": "string"}, "description": {"type": "string"}}}, "description": "Sequence steps"}}, "required": ["entity_type", "entity_id", "steps"]}}},
    # Campaign tools
    {"type": "function", "function": {"name": "send_campaign_to_segment", "description": "Trigger sending a campaign to its members", "parameters": {"type": "object", "properties": {"campaign_id": {"type": "integer", "description": "Campaign to send"}, "segment": {"type": "string", "description": "Segment filter (default all)"}}, "required": ["campaign_id"]}}},
]


SYSTEM_PROMPT_BASE = (
    "You are an autonomous AI sales assistant. You don't just answer questions - you take action. "
    "You can search data, create leads, schedule activities, update statuses, add notes, "
    "generate reports, search quotes and proposals, view payment summaries, get campaign stats, "
    "provide deal coaching, and remember user preferences. "
    "You can also create and send quotes, generate and send proposals, create payment links, "
    "send branded emails, schedule follow-up sequences, analyze the pipeline, and find stale deals. "
    "When a user asks about their pipeline, proactively suggest improvements. "
    "When you notice stale deals, suggest follow-up actions and offer to execute them. "
    "When analyzing opportunities, recommend next steps and offer to create quotes or proposals. "
    "Always be helpful and action-oriented. Propose plans and offer to execute them. "
    "Analyze the user's query and call the appropriate function(s). "
    "For multi-step tasks, call functions one at a time in sequence. "
    "Provide clear, concise responses."
)


class QueryProcessor:
    """
    Processes natural language queries about CRM data.

    Uses GPT-4 to understand intent and generate appropriate responses.
    Implements tiered conversation memory, user preferences,
    multi-step agent loops, and action safety classification.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        import os
        api_key = settings.OPENAI_API_KEY or os.environ.get("OPENAI_API_KEY", "")
        self.client = AsyncOpenAI(api_key=api_key) if api_key else None

        self._conv_manager = AIConversationManager(self.db, self.client)
        self._query_tools = CRMQueryTools(self.db)
        self._action_tools = CRMActionTools(self.db)
        self._analytics_tools = CRMAnalyticsTools(self.db)

    def _build_system_prompt(self, prefs=None, learning_context: str = "") -> str:
        parts = [SYSTEM_PROMPT_BASE]

        if prefs:
            if prefs.preferred_communication_style:
                parts.append(f"Communication style: {prefs.preferred_communication_style}.")
            if prefs.custom_instructions:
                parts.append(f"User instructions: {prefs.custom_instructions}")

        if learning_context:
            parts.append(f"\n\nLearned context about this user:\n{learning_context}")

        return " ".join(parts)

    async def process_query(
        self, query: str, user_id: int, session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        if not self.client:
            return {
                "response": "AI assistant is not configured. Please set OPENAI_API_KEY.",
                "data": None,
            }

        if not session_id:
            session_id = str(uuid.uuid4())

        prefs = await self._conv_manager.get_user_preferences(user_id)
        learning_service = AILearningService(self.db)
        learning_context = await learning_service.get_user_context(user_id)
        history = await self._conv_manager.get_conversation_history(user_id, session_id)
        system_prompt = self._build_system_prompt(prefs, learning_context)

        executor = AIToolExecutor(
            db=self.db,
            openai_client=self.client,
            tools=TOOLS,
            system_prompt=system_prompt,
        )

        return await executor.run(
            query=query,
            user_id=user_id,
            session_id=session_id,
            history=history,
            execute_fn=self._execute_function,
            save_conversation_fn=self._conv_manager.save_conversation,
        )

    async def _log_action(
        self,
        user_id: int,
        session_id: str,
        function_name: str,
        arguments: Dict[str, Any],
        result: Dict[str, Any],
        risk_level: str,
        was_confirmed: bool,
        model_used: str = "gpt-4",
        tokens_used: int = None,
    ) -> None:
        import json
        from src.ai.models import AIActionLog
        result_to_store = result
        result_str = json.dumps(result)
        if len(result_str) > 5000:
            result_to_store = {"truncated": True, "summary": _summarize_result(result)}

        log_entry = AIActionLog(
            user_id=user_id,
            session_id=session_id,
            function_name=function_name,
            arguments=arguments,
            result=result_to_store,
            risk_level=risk_level,
            was_confirmed=was_confirmed,
            model_used=model_used,
            tokens_used=tokens_used,
        )
        self.db.add(log_entry)
        await self.db.flush()

    async def execute_confirmed_action(
        self,
        function_name: str,
        arguments: Dict[str, Any],
        user_id: int,
        session_id: str,
    ) -> Dict[str, Any]:
        data = await self._execute_function(function_name, arguments, user_id)

        risk = classify_action(function_name)
        await self._log_action(
            user_id=user_id,
            session_id=session_id,
            function_name=function_name,
            arguments=arguments,
            result=data,
            risk_level=risk.value,
            was_confirmed=True,
        )

        return {
            "response": f"Action '{function_name}' completed successfully.",
            "data": data,
            "function_called": function_name,
            "actions_taken": [{
                "function": function_name,
                "arguments": arguments,
                "result_summary": _summarize_result(data),
            }],
        }

    async def _execute_function(
        self,
        func_name: str,
        args: Dict[str, Any],
        user_id: int,
    ) -> Dict[str, Any]:
        q = self._query_tools
        a = self._action_tools
        an = self._analytics_tools

        # Read operations
        if func_name == "search_contacts":
            return await q.search_contacts(**args)
        elif func_name == "search_leads":
            return await q.search_leads(**args)
        elif func_name == "get_pipeline_summary":
            return await q.get_pipeline_summary()
        elif func_name == "get_upcoming_tasks":
            return await q.get_upcoming_tasks(user_id, args.get("days", 7))
        elif func_name == "get_recent_activities":
            return await q.get_recent_activities(**args)
        elif func_name == "get_kpis":
            return await q.get_kpis()

        # Write operations
        elif func_name == "create_lead":
            return await a.create_lead(args, user_id)
        elif func_name == "update_lead_status":
            return await a.update_lead_status(args, user_id)
        elif func_name == "create_activity":
            return await a.create_activity(args, user_id)
        elif func_name == "update_opportunity_stage":
            return await a.update_opportunity_stage(args, user_id)
        elif func_name == "add_note":
            return await a.add_note(args, user_id)

        # Report/analytics operations
        elif func_name == "generate_pipeline_report":
            return await an.generate_pipeline_report(args)
        elif func_name == "generate_activity_report":
            return await an.generate_activity_report(args, user_id)

        # Extended read tools
        elif func_name == "search_quotes":
            return await q.search_quotes(args)
        elif func_name == "get_quote_details":
            return await q.get_quote_details(args)
        elif func_name == "search_proposals":
            return await q.search_proposals(args)
        elif func_name == "get_payment_summary":
            return await q.get_payment_summary()
        elif func_name == "list_recent_payments":
            return await q.list_recent_payments(args)
        elif func_name == "get_campaign_stats":
            return await q.get_campaign_stats(args)
        elif func_name == "remember_preference":
            return await a.remember_preference(args, user_id)
        elif func_name == "get_deal_coaching":
            return await q.get_deal_coaching(args)

        # Pipeline intelligence
        elif func_name == "analyze_pipeline":
            return await an.analyze_pipeline(args)
        elif func_name == "suggest_improvements":
            return await an.suggest_improvements(args)
        elif func_name == "get_stale_deals":
            return await an.get_stale_deals(args)
        elif func_name == "get_follow_up_priorities":
            return await an.get_follow_up_priorities(user_id)

        # Execution tools
        elif func_name == "create_and_send_quote":
            return await a.create_and_send_quote(args, user_id)
        elif func_name == "resend_quote":
            return await a.resend_quote(args, user_id)
        elif func_name == "create_and_send_proposal":
            return await a.create_and_send_proposal(args, user_id)
        elif func_name == "resend_proposal":
            return await a.resend_proposal(args, user_id)
        elif func_name == "create_payment_link":
            return await a.create_payment_link(args, user_id)
        elif func_name == "send_invoice":
            return await a.send_invoice(args, user_id)
        elif func_name == "send_email_to_contact":
            return await a.send_email_to_contact(args, user_id)
        elif func_name == "schedule_follow_up_sequence":
            return await a.schedule_follow_up_sequence(args, user_id)
        elif func_name == "send_campaign_to_segment":
            return await a.send_campaign_to_segment(args, user_id)

        else:
            return {"error": f"Unknown function: {func_name}"}
