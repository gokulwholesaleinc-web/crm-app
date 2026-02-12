"""Natural language query processor for AI assistant."""

import json
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta, date, timezone
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from openai import AsyncOpenAI
from src.config import settings
from src.core.filtering import build_token_search
from src.contacts.models import Contact
from src.companies.models import Company
from src.leads.models import Lead
from src.leads.schemas import LeadCreate, LeadUpdate
from src.leads.service import LeadService
from src.opportunities.models import Opportunity, PipelineStage
from src.opportunities.schemas import OpportunityUpdate
from src.opportunities.service import OpportunityService
from src.activities.models import Activity
from src.activities.schemas import ActivityCreate
from src.activities.service import ActivityService
from src.notes.schemas import NoteCreate
from src.notes.service import NoteService
from src.ai.action_safety import classify_action, requires_confirmation, get_confirmation_description, ActionRisk
from src.ai.models import AIActionLog, AIConversation, AIUserPreferences
from src.ai.learning_service import AILearningService

# Tiered memory settings
WORKING_MEMORY_SIZE = 20
SUMMARY_THRESHOLD = 20

# Maximum iterations for multi-step agent loop
MAX_AGENT_ITERATIONS = 10


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

    # =========================================================================
    # Conversation memory (tiered)
    # =========================================================================

    async def _get_user_preferences(self, user_id: int) -> Optional[AIUserPreferences]:
        """Load user preferences for system prompt customization."""
        result = await self.db.execute(
            select(AIUserPreferences).where(AIUserPreferences.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def _get_conversation_history(
        self, user_id: int, session_id: Optional[str] = None
    ) -> List[Dict[str, str]]:
        """Load conversation history with tiered memory.

        Returns the last WORKING_MEMORY_SIZE messages. If the session has more
        messages than SUMMARY_THRESHOLD, older messages are summarized.
        """
        if not session_id:
            return []

        result = await self.db.execute(
            select(AIConversation)
            .where(
                AIConversation.user_id == user_id,
                AIConversation.session_id == session_id,
            )
            .order_by(AIConversation.created_at.asc())
        )
        messages = result.scalars().all()

        if not messages:
            return []

        if len(messages) <= WORKING_MEMORY_SIZE:
            return [
                {"role": m.role, "content": m.content}
                for m in messages
            ]

        older = messages[:-WORKING_MEMORY_SIZE]
        recent = messages[-WORKING_MEMORY_SIZE:]

        summary = await self._summarize_messages(older)

        history = []
        if summary:
            history.append({
                "role": "system",
                "content": f"Summary of earlier conversation: {summary}",
            })

        history.extend(
            {"role": m.role, "content": m.content}
            for m in recent
        )

        return history

    async def _summarize_messages(self, messages: List[AIConversation]) -> Optional[str]:
        """Summarize a list of conversation messages using GPT-4."""
        if not self.client or not messages:
            return None

        conversation_text = "\n".join(
            f"{m.role}: {m.content}" for m in messages
        )

        try:
            response = await self.client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {
                        "role": "system",
                        "content": "Summarize this CRM assistant conversation concisely, preserving key entities, decisions, and context. Keep it under 200 words.",
                    },
                    {"role": "user", "content": conversation_text},
                ],
                max_tokens=300,
            )
            return response.choices[0].message.content
        except Exception:
            return None

    async def _save_conversation(
        self, user_id: int, session_id: Optional[str], role: str, content: str
    ) -> None:
        """Save a conversation message to the database."""
        msg = AIConversation(
            user_id=user_id,
            session_id=session_id,
            role=role,
            content=content,
        )
        self.db.add(msg)
        await self.db.flush()

    def _build_system_prompt(
        self,
        prefs: Optional[AIUserPreferences] = None,
        learning_context: str = "",
    ) -> str:
        """Build system prompt incorporating user preferences and learned context."""
        parts = [SYSTEM_PROMPT_BASE]

        if prefs:
            if prefs.preferred_communication_style:
                parts.append(f"Communication style: {prefs.preferred_communication_style}.")
            if prefs.custom_instructions:
                parts.append(f"User instructions: {prefs.custom_instructions}")

        if learning_context:
            parts.append(f"\n\nLearned context about this user:\n{learning_context}")

        return " ".join(parts)

    # =========================================================================
    # Main query processing with agent loop
    # =========================================================================

    async def process_query(
        self, query: str, user_id: int, session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Process a natural language query and return response.

        Uses the tools API with an agent loop for multi-step tasks.
        Includes tiered conversation memory and user preferences.
        """
        if not self.client:
            return {
                "response": "AI assistant is not configured. Please set OPENAI_API_KEY.",
                "data": None,
            }

        if not session_id:
            session_id = str(uuid.uuid4())

        # Load user preferences, learning context, and conversation history
        prefs = await self._get_user_preferences(user_id)
        learning_service = AILearningService(self.db)
        learning_context = await learning_service.get_user_context(user_id)
        history = await self._get_conversation_history(user_id, session_id)
        system_prompt = self._build_system_prompt(prefs, learning_context)

        # Save user message
        await self._save_conversation(user_id, session_id, "user", query)

        # Build messages with conversation history
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": query})

        actions_taken = []

        try:
            for _iteration in range(MAX_AGENT_ITERATIONS):
                response = await self.client.chat.completions.create(
                    model="gpt-4",
                    messages=messages,
                    tools=TOOLS,
                    tool_choice="auto",
                )

                message = response.choices[0].message

                # No tool calls - model is done, return final text
                if not message.tool_calls:
                    response_text = message.content or ""

                    # Save assistant response
                    await self._save_conversation(
                        user_id, session_id, "assistant", response_text
                    )

                    # Log interaction for learning
                    tool_log = [a for a in actions_taken] if actions_taken else None
                    await learning_service.log_interaction(
                        user_id=user_id,
                        query=query,
                        tool_calls=tool_log,
                    )

                    return {
                        "response": response_text,
                        "data": None,
                        "actions_taken": actions_taken,
                        "session_id": session_id,
                    }

                # Process each tool call
                messages.append(message)

                for tool_call in message.tool_calls:
                    func_name = tool_call.function.name
                    func_args = json.loads(tool_call.function.arguments) if tool_call.function.arguments else {}

                    # Check if action requires confirmation
                    if requires_confirmation(func_name):
                        description = get_confirmation_description(func_name, func_args)
                        # Log the pending action
                        await self._log_action(
                            user_id=user_id,
                            session_id=session_id,
                            function_name=func_name,
                            arguments=func_args,
                            result={"status": "pending_confirmation"},
                            risk_level=classify_action(func_name).value,
                            was_confirmed=False,
                        )
                        return {
                            "response": f"This action requires confirmation: {description}",
                            "data": None,
                            "confirmation_required": True,
                            "pending_action": {
                                "function_name": func_name,
                                "arguments": func_args,
                                "description": description,
                                "session_id": session_id,
                            },
                            "actions_taken": actions_taken,
                            "session_id": session_id,
                        }

                    # Execute the function
                    data = await self._execute_function(func_name, func_args, user_id)

                    # Log the action
                    risk = classify_action(func_name)
                    await self._log_action(
                        user_id=user_id,
                        session_id=session_id,
                        function_name=func_name,
                        arguments=func_args,
                        result=data,
                        risk_level=risk.value,
                        was_confirmed=(risk == ActionRisk.READ),
                    )

                    actions_taken.append({
                        "function": func_name,
                        "arguments": func_args,
                        "result_summary": _summarize_result(data),
                    })

                    # Append tool result to messages for the next iteration
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(data),
                    })

            # If we exhaust iterations, generate a final summary
            final_response = await self.client.chat.completions.create(
                model="gpt-4",
                messages=messages + [
                    {"role": "user", "content": "Please summarize what was accomplished."}
                ],
            )

            response_text = final_response.choices[0].message.content or ""

            # Save assistant response
            await self._save_conversation(
                user_id, session_id, "assistant", response_text
            )

            return {
                "response": response_text,
                "data": None,
                "actions_taken": actions_taken,
                "session_id": session_id,
            }

        except Exception as e:
            return {
                "response": f"I encountered an error processing your request: {str(e)}",
                "data": None,
                "error": str(e),
                "actions_taken": actions_taken,
                "session_id": session_id,
            }

    async def execute_confirmed_action(
        self,
        function_name: str,
        arguments: Dict[str, Any],
        user_id: int,
        session_id: str,
    ) -> Dict[str, Any]:
        """Execute an action that was previously confirmed by the user."""
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

    # =========================================================================
    # Function dispatch
    # =========================================================================

    async def _execute_function(
        self,
        func_name: str,
        args: Dict[str, Any],
        user_id: int,
    ) -> Dict[str, Any]:
        """Execute a function and return results."""

        # Read operations
        if func_name == "search_contacts":
            return await self._search_contacts(**args)
        elif func_name == "search_leads":
            return await self._search_leads(**args)
        elif func_name == "get_pipeline_summary":
            return await self._get_pipeline_summary()
        elif func_name == "get_upcoming_tasks":
            return await self._get_upcoming_tasks(user_id, args.get("days", 7))
        elif func_name == "get_recent_activities":
            return await self._get_recent_activities(**args)
        elif func_name == "get_kpis":
            return await self._get_kpis()

        # Write operations
        elif func_name == "create_lead":
            return await self._create_lead(args, user_id)
        elif func_name == "update_lead_status":
            return await self._update_lead_status(args, user_id)
        elif func_name == "create_activity":
            return await self._create_activity(args, user_id)
        elif func_name == "update_opportunity_stage":
            return await self._update_opportunity_stage(args, user_id)
        elif func_name == "add_note":
            return await self._add_note(args, user_id)

        # Report operations
        elif func_name == "generate_pipeline_report":
            return await self._generate_pipeline_report(args)
        elif func_name == "generate_activity_report":
            return await self._generate_activity_report(args, user_id)

        # Extended tools
        elif func_name == "search_quotes":
            return await self._search_quotes(args)
        elif func_name == "get_quote_details":
            return await self._get_quote_details(args)
        elif func_name == "search_proposals":
            return await self._search_proposals(args)
        elif func_name == "get_payment_summary":
            return await self._get_payment_summary()
        elif func_name == "list_recent_payments":
            return await self._list_recent_payments(args)
        elif func_name == "get_campaign_stats":
            return await self._get_campaign_stats(args)
        elif func_name == "remember_preference":
            return await self._remember_preference(args, user_id)
        elif func_name == "get_deal_coaching":
            return await self._get_deal_coaching(args)

        # Pipeline intelligence
        elif func_name == "analyze_pipeline":
            return await self._analyze_pipeline(args)
        elif func_name == "suggest_improvements":
            return await self._suggest_improvements(args)
        elif func_name == "get_stale_deals":
            return await self._get_stale_deals(args)
        elif func_name == "get_follow_up_priorities":
            return await self._get_follow_up_priorities(user_id)

        # Execution tools
        elif func_name == "create_and_send_quote":
            return await self._create_and_send_quote(args, user_id)
        elif func_name == "resend_quote":
            return await self._resend_quote(args, user_id)
        elif func_name == "create_and_send_proposal":
            return await self._create_and_send_proposal(args, user_id)
        elif func_name == "resend_proposal":
            return await self._resend_proposal(args, user_id)
        elif func_name == "create_payment_link":
            return await self._create_payment_link(args, user_id)
        elif func_name == "send_invoice":
            return await self._send_invoice(args, user_id)
        elif func_name == "send_email_to_contact":
            return await self._send_email_to_contact(args, user_id)
        elif func_name == "schedule_follow_up_sequence":
            return await self._schedule_follow_up_sequence(args, user_id)
        elif func_name == "send_campaign_to_segment":
            return await self._send_campaign_to_segment(args, user_id)

        else:
            return {"error": f"Unknown function: {func_name}"}

    # =========================================================================
    # Read operations
    # =========================================================================

    async def _search_contacts(
        self,
        search_term: str = None,
        company: str = None,
    ) -> Dict[str, Any]:
        """Search contacts."""
        query = select(Contact).limit(10)

        if search_term:
            search_condition = build_token_search(search_term, Contact.first_name, Contact.last_name, Contact.email)
            if search_condition is not None:
                query = query.where(search_condition)

        result = await self.db.execute(query)
        contacts = result.scalars().all()

        return {
            "count": len(contacts),
            "contacts": [
                {
                    "id": c.id,
                    "name": c.full_name,
                    "email": c.email,
                    "phone": c.phone,
                    "job_title": c.job_title,
                }
                for c in contacts
            ],
        }

    async def _search_leads(
        self,
        search_term: str = None,
        status: str = None,
        min_score: int = None,
    ) -> Dict[str, Any]:
        """Search leads."""
        query = select(Lead).limit(10)

        if search_term:
            search_condition = build_token_search(search_term, Lead.first_name, Lead.last_name, Lead.company_name)
            if search_condition is not None:
                query = query.where(search_condition)

        if status:
            query = query.where(Lead.status == status)

        if min_score:
            query = query.where(Lead.score >= min_score)

        result = await self.db.execute(query)
        leads = result.scalars().all()

        return {
            "count": len(leads),
            "leads": [
                {
                    "id": l.id,
                    "name": l.full_name,
                    "company": l.company_name,
                    "status": l.status,
                    "score": l.score,
                }
                for l in leads
            ],
        }

    async def _get_pipeline_summary(self) -> Dict[str, Any]:
        """Get pipeline summary."""
        result = await self.db.execute(
            select(
                PipelineStage.name,
                func.count(Opportunity.id).label("count"),
                func.sum(Opportunity.amount).label("total"),
            )
            .outerjoin(Opportunity)
            .where(PipelineStage.is_active == True)
            .group_by(PipelineStage.id)
            .order_by(PipelineStage.order)
        )

        stages = []
        total_value = 0
        total_deals = 0

        for row in result.all():
            amount = float(row.total or 0)
            stages.append({
                "stage": row.name,
                "deals": row.count or 0,
                "value": amount,
            })
            total_value += amount
            total_deals += row.count or 0

        return {
            "total_deals": total_deals,
            "total_value": total_value,
            "by_stage": stages,
        }

    async def _get_upcoming_tasks(self, user_id: int, days: int = 7) -> Dict[str, Any]:
        """Get upcoming tasks."""
        future = datetime.now() + timedelta(days=days)

        result = await self.db.execute(
            select(Activity)
            .where(
                or_(
                    Activity.owner_id == user_id,
                    Activity.assigned_to_id == user_id,
                )
            )
            .where(Activity.is_completed == False)
            .where(Activity.due_date <= future.date())
            .order_by(Activity.due_date.asc())
            .limit(10)
        )

        tasks = result.scalars().all()

        return {
            "count": len(tasks),
            "tasks": [
                {
                    "id": t.id,
                    "subject": t.subject,
                    "type": t.activity_type,
                    "due_date": t.due_date.isoformat() if t.due_date else None,
                    "priority": t.priority,
                }
                for t in tasks
            ],
        }

    async def _get_recent_activities(
        self,
        entity_type: str = None,
        entity_id: int = None,
        limit: int = 10,
    ) -> Dict[str, Any]:
        """Get recent activities."""
        query = select(Activity).order_by(Activity.created_at.desc()).limit(limit)

        if entity_type and entity_id:
            query = query.where(
                Activity.entity_type == entity_type,
                Activity.entity_id == entity_id,
            )

        result = await self.db.execute(query)
        activities = result.scalars().all()

        return {
            "count": len(activities),
            "activities": [
                {
                    "id": a.id,
                    "type": a.activity_type,
                    "subject": a.subject,
                    "created_at": a.created_at.isoformat(),
                }
                for a in activities
            ],
        }

    async def _get_kpis(self) -> Dict[str, Any]:
        """Get key performance indicators."""
        contacts = await self.db.execute(select(func.count(Contact.id)))
        contacts_count = contacts.scalar() or 0

        leads = await self.db.execute(
            select(func.count(Lead.id)).where(
                Lead.status.in_(["new", "contacted", "qualified"])
            )
        )
        leads_count = leads.scalar() or 0

        pipeline = await self.db.execute(
            select(func.sum(Opportunity.amount))
            .join(PipelineStage)
            .where(PipelineStage.is_won == False, PipelineStage.is_lost == False)
        )
        pipeline_value = float(pipeline.scalar() or 0)

        return {
            "total_contacts": contacts_count,
            "open_leads": leads_count,
            "pipeline_value": pipeline_value,
        }

    # =========================================================================
    # Write operations (reuse existing services)
    # =========================================================================

    async def _create_lead(self, args: Dict[str, Any], user_id: int) -> Dict[str, Any]:
        """Create a new lead using LeadService."""
        service = LeadService(self.db)
        lead_data = LeadCreate(
            first_name=args["first_name"],
            last_name=args["last_name"],
            email=args.get("email"),
            company_name=args.get("company_name"),
            source_details=args.get("source"),
            description=args.get("notes"),
        )
        lead = await service.create(lead_data, user_id)
        return {
            "success": True,
            "lead_id": lead.id,
            "name": lead.full_name,
            "status": lead.status,
            "score": lead.score,
            "message": f"Lead '{lead.full_name}' created successfully.",
        }

    async def _update_lead_status(self, args: Dict[str, Any], user_id: int) -> Dict[str, Any]:
        """Update lead status using LeadService."""
        service = LeadService(self.db)
        lead = await service.get_by_id(args["lead_id"])
        if not lead:
            return {"error": f"Lead with ID {args['lead_id']} not found."}

        old_status = lead.status
        update_data = LeadUpdate(status=args["new_status"])
        if args.get("reason"):
            update_data.description = f"{lead.description or ''}\n\nStatus change ({old_status} -> {args['new_status']}): {args['reason']}".strip()

        lead = await service.update(lead, update_data, user_id)
        return {
            "success": True,
            "lead_id": lead.id,
            "name": lead.full_name,
            "old_status": old_status,
            "new_status": lead.status,
            "message": f"Lead '{lead.full_name}' status changed from '{old_status}' to '{lead.status}'.",
        }

    async def _create_activity(self, args: Dict[str, Any], user_id: int) -> Dict[str, Any]:
        """Create an activity using ActivityService."""
        service = ActivityService(self.db)

        due = None
        if args.get("due_date"):
            try:
                due = date.fromisoformat(args["due_date"])
            except ValueError:
                return {"error": f"Invalid date format: {args['due_date']}. Use YYYY-MM-DD."}

        activity_data = ActivityCreate(
            subject=args["subject"],
            activity_type=args["activity_type"],
            entity_type=args["entity_type"],
            entity_id=args["entity_id"],
            due_date=due,
            priority=args.get("priority", "normal"),
            description=args.get("notes"),
        )
        activity = await service.create(activity_data, user_id)
        return {
            "success": True,
            "activity_id": activity.id,
            "subject": activity.subject,
            "type": activity.activity_type,
            "due_date": activity.due_date.isoformat() if activity.due_date else None,
            "message": f"Activity '{activity.subject}' created successfully.",
        }

    async def _update_opportunity_stage(self, args: Dict[str, Any], user_id: int) -> Dict[str, Any]:
        """Move an opportunity to a different pipeline stage using OpportunityService."""
        service = OpportunityService(self.db)
        opportunity = await service.get_by_id(args["opportunity_id"])
        if not opportunity:
            return {"error": f"Opportunity with ID {args['opportunity_id']} not found."}

        # Verify the target stage exists
        stage_result = await self.db.execute(
            select(PipelineStage).where(PipelineStage.id == args["stage_id"])
        )
        stage = stage_result.scalar_one_or_none()
        if not stage:
            return {"error": f"Pipeline stage with ID {args['stage_id']} not found."}

        old_stage_name = "Unknown"
        if opportunity.pipeline_stage:
            old_stage_name = opportunity.pipeline_stage.name

        update_data = OpportunityUpdate(pipeline_stage_id=args["stage_id"])
        if args.get("notes"):
            desc = opportunity.description or ""
            update_data.description = f"{desc}\n\nStage change: {args['notes']}".strip()

        opportunity = await service.update(opportunity, update_data, user_id)
        return {
            "success": True,
            "opportunity_id": opportunity.id,
            "name": opportunity.name,
            "old_stage": old_stage_name,
            "new_stage": stage.name,
            "message": f"Opportunity '{opportunity.name}' moved from '{old_stage_name}' to '{stage.name}'.",
        }

    async def _add_note(self, args: Dict[str, Any], user_id: int) -> Dict[str, Any]:
        """Add a note to an entity using NoteService."""
        service = NoteService(self.db)
        note_data = NoteCreate(
            entity_type=args["entity_type"],
            entity_id=args["entity_id"],
            content=args["content"],
        )
        note = await service.create(note_data, user_id)
        return {
            "success": True,
            "note_id": note["id"],
            "entity_type": args["entity_type"],
            "entity_id": args["entity_id"],
            "message": f"Note added to {args['entity_type']} #{args['entity_id']}.",
        }

    # =========================================================================
    # Report operations
    # =========================================================================

    async def _generate_pipeline_report(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Generate a detailed pipeline report for a date range."""
        date_from = None
        date_to = None

        if args.get("date_from"):
            try:
                date_from = date.fromisoformat(args["date_from"])
            except ValueError:
                pass
        if args.get("date_to"):
            try:
                date_to = date.fromisoformat(args["date_to"])
            except ValueError:
                pass

        query = (
            select(
                PipelineStage.name,
                PipelineStage.probability,
                func.count(Opportunity.id).label("count"),
                func.sum(Opportunity.amount).label("total"),
                func.avg(Opportunity.amount).label("avg_amount"),
            )
            .outerjoin(Opportunity)
            .where(PipelineStage.is_active == True)
        )

        if date_from:
            query = query.where(Opportunity.created_at >= datetime.combine(date_from, datetime.min.time()))
        if date_to:
            query = query.where(Opportunity.created_at <= datetime.combine(date_to, datetime.max.time()))

        query = query.group_by(PipelineStage.id).order_by(PipelineStage.order)
        result = await self.db.execute(query)

        stages = []
        total_value = 0
        total_weighted = 0
        total_deals = 0

        for row in result.all():
            amount = float(row.total or 0)
            avg = float(row.avg_amount or 0)
            weighted = amount * (row.probability / 100)
            stages.append({
                "stage": row.name,
                "deals": row.count or 0,
                "total_value": amount,
                "avg_deal_size": round(avg, 2),
                "probability": row.probability,
                "weighted_value": round(weighted, 2),
            })
            total_value += amount
            total_weighted += weighted
            total_deals += row.count or 0

        return {
            "report_type": "pipeline",
            "date_from": args.get("date_from"),
            "date_to": args.get("date_to"),
            "total_deals": total_deals,
            "total_value": total_value,
            "total_weighted_value": round(total_weighted, 2),
            "by_stage": stages,
        }

    async def _generate_activity_report(self, args: Dict[str, Any], user_id: int) -> Dict[str, Any]:
        """Generate an activity summary report."""
        report_user_id = args.get("user_id", user_id)
        date_from = None
        date_to = None

        if args.get("date_from"):
            try:
                date_from = date.fromisoformat(args["date_from"])
            except ValueError:
                pass
        if args.get("date_to"):
            try:
                date_to = date.fromisoformat(args["date_to"])
            except ValueError:
                pass

        query = select(Activity).where(
            or_(
                Activity.owner_id == report_user_id,
                Activity.assigned_to_id == report_user_id,
            )
        )

        if date_from:
            query = query.where(Activity.created_at >= datetime.combine(date_from, datetime.min.time()))
        if date_to:
            query = query.where(Activity.created_at <= datetime.combine(date_to, datetime.max.time()))

        result = await self.db.execute(query)
        activities = result.scalars().all()

        by_type = {}
        completed = 0
        pending = 0
        for a in activities:
            by_type[a.activity_type] = by_type.get(a.activity_type, 0) + 1
            if a.is_completed:
                completed += 1
            else:
                pending += 1

        return {
            "report_type": "activity",
            "user_id": report_user_id,
            "date_from": args.get("date_from"),
            "date_to": args.get("date_to"),
            "total_activities": len(activities),
            "completed": completed,
            "pending": pending,
            "by_type": by_type,
        }

    # =========================================================================
    # Extended tool implementations
    # =========================================================================

    async def _search_quotes(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Search quotes."""
        from src.quotes.models import Quote

        query = select(Quote).order_by(Quote.created_at.desc()).limit(args.get("limit", 10))

        if args.get("status"):
            query = query.where(Quote.status == args["status"])

        if args.get("search_term"):
            search_condition = build_token_search(args["search_term"], Quote.title)
            if search_condition is not None:
                query = query.where(search_condition)

        result = await self.db.execute(query)
        quotes = result.scalars().all()

        return {
            "count": len(quotes),
            "quotes": [
                {
                    "id": q.id,
                    "title": q.title,
                    "quote_number": q.quote_number,
                    "status": q.status,
                    "total": float(q.total) if q.total else 0,
                    "valid_until": q.valid_until.isoformat() if q.valid_until else None,
                }
                for q in quotes
            ],
        }

    async def _get_quote_details(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Get full details of a quote."""
        from src.quotes.models import Quote

        result = await self.db.execute(
            select(Quote).where(Quote.id == args["quote_id"])
        )
        quote = result.scalar_one_or_none()
        if not quote:
            return {"error": f"Quote with ID {args['quote_id']} not found."}

        return {
            "id": quote.id,
            "title": quote.title,
            "quote_number": quote.quote_number,
            "status": quote.status,
            "subtotal": float(quote.subtotal) if quote.subtotal else 0,
            "tax_amount": float(quote.tax_amount) if quote.tax_amount else 0,
            "total": float(quote.total) if quote.total else 0,
            "valid_until": quote.valid_until.isoformat() if quote.valid_until else None,
            "payment_type": getattr(quote, "payment_type", None),
            "line_items": [
                {
                    "description": li.description,
                    "quantity": li.quantity,
                    "unit_price": float(li.unit_price) if li.unit_price else 0,
                    "total": float(li.total) if li.total else 0,
                }
                for li in (quote.line_items or [])
            ],
        }

    async def _search_proposals(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Search proposals."""
        from src.proposals.models import Proposal

        query = select(Proposal).order_by(Proposal.created_at.desc()).limit(args.get("limit", 10))

        if args.get("status"):
            query = query.where(Proposal.status == args["status"])

        if args.get("search_term"):
            search_condition = build_token_search(args["search_term"], Proposal.title)
            if search_condition is not None:
                query = query.where(search_condition)

        result = await self.db.execute(query)
        proposals = result.scalars().all()

        return {
            "count": len(proposals),
            "proposals": [
                {
                    "id": p.id,
                    "title": p.title,
                    "status": p.status,
                    "created_at": p.created_at.isoformat() if p.created_at else None,
                }
                for p in proposals
            ],
        }

    async def _get_payment_summary(self) -> Dict[str, Any]:
        """Get payment summary."""
        from src.payments.models import Payment

        result = await self.db.execute(
            select(
                Payment.status,
                func.count(Payment.id).label("count"),
                func.sum(Payment.amount).label("total"),
            ).group_by(Payment.status)
        )

        by_status = {}
        grand_total = 0
        total_count = 0
        for row in result.all():
            amount = float(row.total or 0)
            by_status[row.status] = {
                "count": row.count or 0,
                "total": amount,
            }
            grand_total += amount
            total_count += row.count or 0

        return {
            "total_payments": total_count,
            "total_amount": grand_total,
            "by_status": by_status,
        }

    async def _list_recent_payments(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """List recent payments."""
        from src.payments.models import Payment

        query = select(Payment).order_by(Payment.created_at.desc()).limit(args.get("limit", 10))

        if args.get("status"):
            query = query.where(Payment.status == args["status"])

        result = await self.db.execute(query)
        payments = result.scalars().all()

        return {
            "count": len(payments),
            "payments": [
                {
                    "id": p.id,
                    "amount": float(p.amount) if p.amount else 0,
                    "status": p.status,
                    "payment_date": p.payment_date.isoformat() if p.payment_date else None,
                    "created_at": p.created_at.isoformat() if p.created_at else None,
                }
                for p in payments
            ],
        }

    async def _get_campaign_stats(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Get campaign statistics."""
        from src.campaigns.models import Campaign

        if args.get("campaign_id"):
            result = await self.db.execute(
                select(Campaign).where(Campaign.id == args["campaign_id"])
            )
            campaign = result.scalar_one_or_none()
            if not campaign:
                return {"error": f"Campaign with ID {args['campaign_id']} not found."}

            return {
                "id": campaign.id,
                "name": campaign.name,
                "status": campaign.status,
                "type": getattr(campaign, "campaign_type", None),
                "start_date": campaign.start_date.isoformat() if campaign.start_date else None,
                "end_date": campaign.end_date.isoformat() if campaign.end_date else None,
            }

        # Return overview
        result = await self.db.execute(
            select(
                Campaign.status,
                func.count(Campaign.id).label("count"),
            ).group_by(Campaign.status)
        )

        by_status = {}
        total = 0
        for row in result.all():
            by_status[row.status] = row.count or 0
            total += row.count or 0

        return {"total_campaigns": total, "by_status": by_status}

    async def _remember_preference(self, args: Dict[str, Any], user_id: int) -> Dict[str, Any]:
        """Remember a user preference."""
        learning_service = AILearningService(self.db)
        learning = await learning_service.learn_preference(
            user_id=user_id,
            category=args["category"],
            key=args["key"],
            value=args["value"],
        )
        return {
            "success": True,
            "message": f"Remembered: {args['key']} = {args['value']}",
            "learning_id": learning.id,
        }

    async def _get_deal_coaching(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Get coaching tips for an opportunity."""
        result = await self.db.execute(
            select(Opportunity).where(Opportunity.id == args["opportunity_id"])
        )
        opp = result.scalar_one_or_none()
        if not opp:
            return {"error": f"Opportunity with ID {args['opportunity_id']} not found."}

        tips = []

        # Check activity level
        activity_result = await self.db.execute(
            select(func.count(Activity.id))
            .where(Activity.entity_type == "opportunities")
            .where(Activity.entity_id == opp.id)
        )
        activity_count = activity_result.scalar() or 0

        if activity_count == 0:
            tips.append("No activities recorded. Schedule an initial meeting or call.")
        elif activity_count < 3:
            tips.append("Low activity. Increase engagement with more touchpoints.")

        # Check close date
        if opp.expected_close_date:
            days_to_close = (opp.expected_close_date - date.today()).days
            if days_to_close < 0:
                tips.append(f"Deal is {abs(days_to_close)} days overdue. Re-evaluate or update the close date.")
            elif days_to_close <= 7:
                tips.append(f"Closing in {days_to_close} days. Push for a decision.")
            elif days_to_close <= 30:
                tips.append("Closing within a month. Ensure all stakeholders are aligned.")

        # Check contact
        if not opp.contact_id:
            tips.append("No contact assigned. Associate a decision maker.")

        if not tips:
            tips.append("Deal looks healthy. Continue current engagement strategy.")

        return {
            "opportunity_id": opp.id,
            "name": opp.name,
            "amount": float(opp.amount) if opp.amount else 0,
            "coaching_tips": tips,
        }

    # =========================================================================
    # Pipeline intelligence tools
    # =========================================================================

    async def _analyze_pipeline(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze the sales pipeline with detailed insights."""
        days = args.get("days", 30)
        now = datetime.now()
        period_start = now - timedelta(days=days)
        prev_period_start = period_start - timedelta(days=days)

        # Current period deals
        result = await self.db.execute(
            select(
                PipelineStage.name,
                PipelineStage.probability,
                PipelineStage.is_won,
                PipelineStage.is_lost,
                func.count(Opportunity.id).label("count"),
                func.sum(Opportunity.amount).label("total"),
                func.avg(Opportunity.amount).label("avg_amount"),
            )
            .outerjoin(Opportunity)
            .where(PipelineStage.is_active == True)
            .group_by(PipelineStage.id)
            .order_by(PipelineStage.order)
        )

        stages = []
        total_value = 0
        total_deals = 0
        weighted_value = 0
        won_count = 0
        lost_count = 0
        open_count = 0

        for row in result.all():
            amount = float(row.total or 0)
            avg = float(row.avg_amount or 0)
            w_value = amount * (row.probability / 100)
            count = row.count or 0

            stages.append({
                "stage": row.name,
                "deals": count,
                "total_value": amount,
                "avg_deal_size": round(avg, 2),
                "probability": row.probability,
                "weighted_value": round(w_value, 2),
            })
            total_value += amount
            total_deals += count
            weighted_value += w_value

            if row.is_won:
                won_count += count
            elif row.is_lost:
                lost_count += count
            else:
                open_count += count

        # Win rate
        closed = won_count + lost_count
        win_rate = round((won_count / closed * 100), 1) if closed > 0 else None

        # Deals at risk (no activity in last 7 days)
        stale_cutoff = now - timedelta(days=7)
        stale_result = await self.db.execute(
            select(func.count(Opportunity.id))
            .join(PipelineStage)
            .where(
                PipelineStage.is_won == False,
                PipelineStage.is_lost == False,
            )
            .where(
                ~Opportunity.id.in_(
                    select(Activity.entity_id)
                    .where(Activity.entity_type == "opportunities")
                    .where(Activity.created_at > stale_cutoff)
                )
            )
        )
        deals_at_risk = stale_result.scalar() or 0

        # Upcoming close dates (next 14 days)
        upcoming_cutoff = (now + timedelta(days=14)).date()
        upcoming_result = await self.db.execute(
            select(func.count(Opportunity.id))
            .join(PipelineStage)
            .where(
                PipelineStage.is_won == False,
                PipelineStage.is_lost == False,
                Opportunity.expected_close_date <= upcoming_cutoff,
                Opportunity.expected_close_date >= now.date(),
            )
        )
        upcoming_closes = upcoming_result.scalar() or 0

        # Previous period comparison
        prev_result = await self.db.execute(
            select(
                func.count(Opportunity.id).label("count"),
                func.sum(Opportunity.amount).label("total"),
            )
            .join(PipelineStage)
            .where(
                Opportunity.created_at >= datetime.combine(prev_period_start.date(), datetime.min.time()),
                Opportunity.created_at < datetime.combine(period_start.date(), datetime.min.time()),
                PipelineStage.is_won == True,
            )
        )
        prev_row = prev_result.one_or_none()
        prev_won_value = float(prev_row.total or 0) if prev_row else 0

        cur_result = await self.db.execute(
            select(func.sum(Opportunity.amount))
            .join(PipelineStage)
            .where(
                Opportunity.created_at >= datetime.combine(period_start.date(), datetime.min.time()),
                PipelineStage.is_won == True,
            )
        )
        cur_won_value = float(cur_result.scalar() or 0)

        recommendations = []
        if deals_at_risk > 0:
            recommendations.append(f"{deals_at_risk} deal(s) have no recent activity - follow up immediately.")
        if upcoming_closes > 0:
            recommendations.append(f"{upcoming_closes} deal(s) closing in the next 14 days - push for decisions.")
        if win_rate is not None and win_rate < 30:
            recommendations.append("Win rate is below 30% - review qualification criteria.")
        if open_count > 0 and total_value > 0:
            avg_deal = total_value / open_count
            recommendations.append(f"Average open deal size: ${avg_deal:,.0f}.")

        return {
            "analysis_period_days": days,
            "total_deals": total_deals,
            "open_deals": open_count,
            "won_deals": won_count,
            "lost_deals": lost_count,
            "total_pipeline_value": total_value,
            "weighted_forecast": round(weighted_value, 2),
            "win_rate_percent": win_rate,
            "avg_deal_size": round(total_value / total_deals, 2) if total_deals > 0 else 0,
            "deals_at_risk": deals_at_risk,
            "upcoming_closes_14d": upcoming_closes,
            "current_period_won_value": cur_won_value,
            "previous_period_won_value": prev_won_value,
            "by_stage": stages,
            "recommendations": recommendations,
        }

    async def _suggest_improvements(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Propose improvement plan for a specific deal or the whole pipeline."""
        opportunity_id = args.get("opportunity_id")

        if opportunity_id:
            # Specific opportunity improvement plan
            result = await self.db.execute(
                select(Opportunity).where(Opportunity.id == opportunity_id)
            )
            opp = result.scalar_one_or_none()
            if not opp:
                return {"error": f"Opportunity with ID {opportunity_id} not found."}

            # Get activity count
            act_result = await self.db.execute(
                select(func.count(Activity.id))
                .where(Activity.entity_type == "opportunities", Activity.entity_id == opp.id)
            )
            activity_count = act_result.scalar() or 0

            # Recent activity
            week_ago = datetime.now() - timedelta(days=7)
            recent_result = await self.db.execute(
                select(func.count(Activity.id))
                .where(
                    Activity.entity_type == "opportunities",
                    Activity.entity_id == opp.id,
                    Activity.created_at > week_ago,
                )
            )
            recent_count = recent_result.scalar() or 0

            suggestions = []
            risk_factors = []

            if activity_count == 0:
                risk_factors.append("No activities recorded at all.")
                suggestions.append("Schedule an initial call or meeting immediately.")
            elif recent_count == 0:
                risk_factors.append("No activity in the past week.")
                suggestions.append("Re-engage with a follow-up call or email.")

            if not opp.contact_id:
                risk_factors.append("No contact assigned to this deal.")
                suggestions.append("Associate a decision-maker contact.")

            if opp.expected_close_date:
                days_to_close = (opp.expected_close_date - date.today()).days
                if days_to_close < 0:
                    risk_factors.append(f"Deal is {abs(days_to_close)} days overdue.")
                    suggestions.append("Update the close date or re-qualify the opportunity.")
                elif days_to_close <= 7:
                    suggestions.append("Closing soon - send a proposal or finalize terms.")

            if float(opp.amount or 0) > 0 and activity_count < 3:
                suggestions.append("Increase engagement - schedule more touchpoints for this deal value.")

            if not risk_factors:
                risk_factors.append("No major risks identified.")
            if not suggestions:
                suggestions.append("Deal looks healthy. Maintain current engagement strategy.")

            return {
                "opportunity_id": opp.id,
                "name": opp.name,
                "amount": float(opp.amount) if opp.amount else 0,
                "activity_count": activity_count,
                "recent_activity_count": recent_count,
                "risk_factors": risk_factors,
                "suggested_actions": suggestions,
            }

        # Full pipeline improvement suggestions
        pipeline_analysis = await self._analyze_pipeline({"days": 30})

        suggestions = []

        # Identify bottleneck stages (high count, low conversion)
        stages = pipeline_analysis.get("by_stage", [])
        for i, stage in enumerate(stages):
            if stage["deals"] > 5 and stage.get("probability", 0) < 50:
                suggestions.append(
                    f"Stage '{stage['stage']}' has {stage['deals']} deals but low probability - "
                    f"review qualification criteria for this stage."
                )

        if pipeline_analysis.get("deals_at_risk", 0) > 0:
            suggestions.append(
                f"Follow up on {pipeline_analysis['deals_at_risk']} stale deal(s) immediately."
            )

        if pipeline_analysis.get("win_rate_percent") and pipeline_analysis["win_rate_percent"] < 25:
            suggestions.append(
                "Win rate is low. Consider tightening lead qualification criteria."
            )

        if pipeline_analysis.get("upcoming_closes_14d", 0) > 0:
            suggestions.append(
                f"Prioritize {pipeline_analysis['upcoming_closes_14d']} deals closing within 14 days."
            )

        if not suggestions:
            suggestions.append("Pipeline looks healthy. Continue current strategies.")

        return {
            "pipeline_summary": {
                "total_value": pipeline_analysis["total_pipeline_value"],
                "open_deals": pipeline_analysis["open_deals"],
                "win_rate": pipeline_analysis["win_rate_percent"],
                "weighted_forecast": pipeline_analysis["weighted_forecast"],
            },
            "improvement_suggestions": suggestions,
        }

    async def _get_stale_deals(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Find opportunities with no recent activity."""
        days_idle = args.get("days_idle", 7)
        cutoff = datetime.now() - timedelta(days=days_idle)

        # Find open opportunities with no activity since cutoff
        active_opp_ids = (
            select(Activity.entity_id)
            .where(Activity.entity_type == "opportunities")
            .where(Activity.created_at > cutoff)
        )

        result = await self.db.execute(
            select(Opportunity)
            .join(PipelineStage)
            .where(
                PipelineStage.is_won == False,
                PipelineStage.is_lost == False,
                ~Opportunity.id.in_(active_opp_ids),
            )
            .order_by(Opportunity.amount.desc().nullslast())
            .limit(20)
        )
        stale_opps = result.scalars().all()

        deals = []
        for opp in stale_opps:
            # Get last activity date
            last_act = await self.db.execute(
                select(Activity.created_at)
                .where(Activity.entity_type == "opportunities", Activity.entity_id == opp.id)
                .order_by(Activity.created_at.desc())
                .limit(1)
            )
            last_activity_row = last_act.scalar_one_or_none()
            last_activity_date = last_activity_row.isoformat() if last_activity_row else None

            suggestion = "Schedule a follow-up call."
            if float(opp.amount or 0) > 10000:
                suggestion = "High-value deal - prioritize a meeting or proposal."
            if opp.expected_close_date and opp.expected_close_date < date.today():
                suggestion = "Deal is overdue - re-qualify or close it."

            deals.append({
                "id": opp.id,
                "name": opp.name,
                "amount": float(opp.amount) if opp.amount else 0,
                "expected_close_date": opp.expected_close_date.isoformat() if opp.expected_close_date else None,
                "last_activity_date": last_activity_date,
                "suggested_action": suggestion,
            })

        return {
            "days_idle_threshold": days_idle,
            "stale_deals_count": len(deals),
            "deals": deals,
        }

    async def _get_follow_up_priorities(self, user_id: int) -> Dict[str, Any]:
        """Rank contacts/leads by follow-up urgency."""
        priorities = []

        # Get open opportunities with contacts, ordered by urgency
        result = await self.db.execute(
            select(Opportunity)
            .join(PipelineStage)
            .where(
                Opportunity.owner_id == user_id,
                PipelineStage.is_won == False,
                PipelineStage.is_lost == False,
            )
            .order_by(Opportunity.expected_close_date.asc().nullslast())
            .limit(20)
        )
        opportunities = result.scalars().all()

        for opp in opportunities:
            # Get last activity date
            last_act = await self.db.execute(
                select(Activity.created_at)
                .where(Activity.entity_type == "opportunities", Activity.entity_id == opp.id)
                .order_by(Activity.created_at.desc())
                .limit(1)
            )
            last_act_date = last_act.scalar_one_or_none()

            days_since_contact = None
            if last_act_date:
                days_since_contact = (datetime.now(last_act_date.tzinfo) - last_act_date).days if last_act_date.tzinfo else (datetime.now() - last_act_date).days

            # Calculate urgency score (higher = more urgent)
            urgency = 0
            reasons = []

            if days_since_contact is None:
                urgency += 50
                reasons.append("Never contacted")
            elif days_since_contact > 14:
                urgency += 40
                reasons.append(f"No contact in {days_since_contact} days")
            elif days_since_contact > 7:
                urgency += 20
                reasons.append(f"Last contact {days_since_contact} days ago")

            if opp.expected_close_date:
                days_to_close = (opp.expected_close_date - date.today()).days
                if days_to_close < 0:
                    urgency += 30
                    reasons.append("Past expected close date")
                elif days_to_close <= 7:
                    urgency += 25
                    reasons.append(f"Closing in {days_to_close} days")
                elif days_to_close <= 14:
                    urgency += 15
                    reasons.append(f"Closing in {days_to_close} days")

            amount = float(opp.amount or 0)
            if amount > 50000:
                urgency += 15
                reasons.append("High-value deal")
            elif amount > 10000:
                urgency += 10

            suggestion = "Send a follow-up email."
            if urgency > 60:
                suggestion = "Urgent: schedule a call or meeting immediately."
            elif urgency > 30:
                suggestion = "Schedule a follow-up call this week."

            priorities.append({
                "opportunity_id": opp.id,
                "opportunity_name": opp.name,
                "amount": amount,
                "contact_id": opp.contact_id,
                "days_since_last_contact": days_since_contact,
                "expected_close_date": opp.expected_close_date.isoformat() if opp.expected_close_date else None,
                "urgency_score": urgency,
                "reasons": reasons,
                "suggested_action": suggestion,
            })

        priorities.sort(key=lambda x: x["urgency_score"], reverse=True)

        return {
            "count": len(priorities),
            "priorities": priorities,
        }

    # =========================================================================
    # Execution tools
    # =========================================================================

    async def _create_and_send_quote(self, args: Dict[str, Any], user_id: int) -> Dict[str, Any]:
        """Create a quote with line items and optionally send it via public link."""
        from src.quotes.service import QuoteService
        from src.quotes.schemas import QuoteCreate, QuoteLineItemCreate
        import os

        valid_days = args.get("valid_days", 30)
        valid_until = (date.today() + timedelta(days=valid_days))

        line_items = []
        for item in (args.get("line_items") or []):
            line_items.append(QuoteLineItemCreate(
                description=item.get("description", "Item"),
                quantity=item.get("quantity", 1),
                unit_price=item.get("unit_price", 0),
            ))

        quote_data = QuoteCreate(
            title=args["title"],
            contact_id=args["contact_id"],
            opportunity_id=args.get("opportunity_id"),
            valid_until=valid_until,
            line_items=line_items if line_items else None,
            owner_id=user_id,
        )

        service = QuoteService(self.db)
        quote = await service.create(quote_data, user_id)

        base_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
        public_url = f"{base_url}/quotes/public/{quote.quote_number}"

        result = {
            "success": True,
            "quote_id": quote.id,
            "quote_number": quote.quote_number,
            "total": float(quote.total) if quote.total else 0,
            "status": quote.status,
            "valid_until": valid_until.isoformat(),
            "public_url": public_url,
            "message": f"Quote '{quote.quote_number}' created successfully.",
        }

        if args.get("send_immediately"):
            send_result = await self._send_quote_email(quote, user_id)
            result["email_sent"] = send_result.get("success", False)
            result["status"] = "sent" if send_result.get("success") else result["status"]
            result["message"] += f" Email {'sent with public link' if send_result.get('success') else 'failed'}."

        return result

    async def _send_quote_email(self, quote, user_id: int) -> Dict[str, Any]:
        """Send a quote email with public link using branded templates."""
        import os

        if not quote.contact_id:
            return {"success": False, "error": "No contact associated with quote."}

        contact_result = await self.db.execute(
            select(Contact).where(Contact.id == quote.contact_id)
        )
        contact = contact_result.scalar_one_or_none()
        if not contact or not contact.email:
            return {"success": False, "error": "Contact has no email address."}

        from src.email.branded_templates import TenantBrandingHelper, render_quote_email
        from src.email.service import EmailService

        branding = await TenantBrandingHelper.get_branding_for_user(self.db, user_id)

        # Build public view URL for the CTA button in the email
        base_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
        view_url = f"{base_url}/quotes/public/{quote.quote_number}"

        quote_data = {
            "quote_number": quote.quote_number,
            "client_name": contact.full_name,
            "total": str(float(quote.total) if quote.total else "0.00"),
            "currency": quote.currency or "USD",
            "valid_until": quote.valid_until.isoformat() if quote.valid_until else "",
            "items": [
                {
                    "description": li.description,
                    "quantity": str(li.quantity),
                    "unit_price": str(float(li.unit_price) if li.unit_price else "0"),
                    "total": str(float(li.total) if li.total else "0"),
                }
                for li in (quote.line_items or [])
            ],
            "view_url": view_url,
        }
        subject, html_body = render_quote_email(branding, quote_data)

        email_service = EmailService(self.db)
        await email_service.queue_email(
            to_email=contact.email,
            subject=subject,
            body=html_body,
            sent_by_id=user_id,
            entity_type="quotes",
            entity_id=quote.id,
        )

        # Transition quote status to sent
        if quote.status == "draft":
            quote.status = "sent"
            quote.sent_at = datetime.now(timezone.utc)
            await self.db.flush()

        return {"success": True}

    async def _resend_quote(self, args: Dict[str, Any], user_id: int) -> Dict[str, Any]:
        """Resend an existing quote to the client."""
        from src.quotes.models import Quote
        from sqlalchemy.orm import selectinload

        result = await self.db.execute(
            select(Quote)
            .options(selectinload(Quote.line_items))
            .where(Quote.id == args["quote_id"])
        )
        quote = result.scalar_one_or_none()
        if not quote:
            return {"error": f"Quote with ID {args['quote_id']} not found."}

        send_result = await self._send_quote_email(quote, user_id)
        if send_result.get("success"):
            return {"success": True, "message": f"Quote '{quote.quote_number}' resent successfully."}
        return {"success": False, "error": send_result.get("error", "Failed to send email.")}

    async def _create_and_send_proposal(self, args: Dict[str, Any], user_id: int) -> Dict[str, Any]:
        """Generate an AI proposal and optionally send it."""
        from src.proposals.service import ProposalService
        from src.proposals.schemas import ProposalCreate

        opp_result = await self.db.execute(
            select(Opportunity).where(Opportunity.id == args["opportunity_id"])
        )
        opp = opp_result.scalar_one_or_none()
        if not opp:
            return {"error": f"Opportunity with ID {args['opportunity_id']} not found."}

        proposal_data = ProposalCreate(
            title=f"Proposal for {opp.name}",
            opportunity_id=opp.id,
            contact_id=opp.contact_id,
            company_id=opp.company_id,
            executive_summary=f"We are pleased to present this proposal for {opp.name}.",
            pricing_section=f"Proposed investment: {opp.currency or 'USD'} {float(opp.amount or 0):,.2f}",
            owner_id=user_id,
        )

        service = ProposalService(self.db)
        proposal = await service.create(proposal_data, user_id)

        result = {
            "success": True,
            "proposal_id": proposal.id,
            "proposal_number": proposal.proposal_number,
            "title": proposal.title,
            "status": proposal.status,
            "message": f"Proposal '{proposal.proposal_number}' created successfully.",
        }

        if args.get("send_immediately") and opp.contact_id:
            send_result = await self._send_proposal_email(proposal, opp, user_id)
            result["email_sent"] = send_result.get("success", False)
            result["message"] += f" Email {'sent' if send_result.get('success') else 'failed'}."

        return result

    async def _send_proposal_email(self, proposal, opportunity, user_id: int) -> Dict[str, Any]:
        """Send a proposal email using branded templates."""
        if not opportunity.contact_id:
            return {"success": False, "error": "No contact on opportunity."}

        contact_result = await self.db.execute(
            select(Contact).where(Contact.id == opportunity.contact_id)
        )
        contact = contact_result.scalar_one_or_none()
        if not contact or not contact.email:
            return {"success": False, "error": "Contact has no email address."}

        from src.email.branded_templates import TenantBrandingHelper, render_proposal_email
        from src.email.service import EmailService

        branding = await TenantBrandingHelper.get_branding_for_user(self.db, user_id)
        proposal_data = {
            "proposal_title": proposal.title,
            "client_name": contact.full_name,
            "summary": proposal.executive_summary or "",
            "total": str(float(opportunity.amount or 0)),
            "currency": opportunity.currency or "USD",
        }
        subject, html_body = render_proposal_email(branding, proposal_data)

        email_service = EmailService(self.db)
        await email_service.queue_email(
            to_email=contact.email,
            subject=subject,
            body=html_body,
            sent_by_id=user_id,
            entity_type="proposals",
            entity_id=proposal.id,
        )
        return {"success": True}

    async def _resend_proposal(self, args: Dict[str, Any], user_id: int) -> Dict[str, Any]:
        """Resend an existing proposal to the client."""
        from src.proposals.models import Proposal

        result = await self.db.execute(
            select(Proposal).where(Proposal.id == args["proposal_id"])
        )
        proposal = result.scalar_one_or_none()
        if not proposal:
            return {"error": f"Proposal with ID {args['proposal_id']} not found."}

        if not proposal.opportunity_id:
            return {"error": "Proposal has no associated opportunity."}

        opp_result = await self.db.execute(
            select(Opportunity).where(Opportunity.id == proposal.opportunity_id)
        )
        opp = opp_result.scalar_one_or_none()
        if not opp:
            return {"error": "Associated opportunity not found."}

        send_result = await self._send_proposal_email(proposal, opp, user_id)
        if send_result.get("success"):
            return {"success": True, "message": f"Proposal '{proposal.proposal_number}' resent successfully."}
        return {"success": False, "error": send_result.get("error", "Failed to send email.")}

    async def _create_payment_link(self, args: Dict[str, Any], user_id: int) -> Dict[str, Any]:
        """Create a Stripe checkout link and optionally email it."""
        from src.payments.service import PaymentService

        amount = args["amount"]
        currency = args.get("currency", "USD")
        contact_id = args.get("contact_id")
        quote_id = args.get("quote_id")
        description = args.get("description", f"Payment of {currency} {amount}")

        payment_service = PaymentService(self.db)

        # Sync customer if contact provided
        customer_id = None
        if contact_id:
            customer = await payment_service.sync_customer(contact_id=contact_id)
            customer_id = customer.id

        try:
            checkout = await payment_service.create_checkout_session(
                amount=amount,
                currency=currency,
                success_url="https://app.crm.local/payments/success",
                cancel_url="https://app.crm.local/payments/cancel",
                user_id=user_id,
                customer_id=customer_id,
                quote_id=quote_id,
            )
        except ValueError as e:
            return {"error": str(e)}

        result = {
            "success": True,
            "checkout_url": checkout.get("checkout_url", ""),
            "checkout_session_id": checkout.get("checkout_session_id", ""),
            "amount": amount,
            "currency": currency,
            "message": f"Payment link created for {currency} {amount:,.2f}.",
        }

        # Email the link to the contact if requested
        if contact_id and checkout.get("checkout_url"):
            contact_result = await self.db.execute(
                select(Contact).where(Contact.id == contact_id)
            )
            contact = contact_result.scalar_one_or_none()
            if contact and contact.email:
                from src.email.branded_templates import TenantBrandingHelper, render_branded_email
                from src.email.service import EmailService

                branding = await TenantBrandingHelper.get_branding_for_user(self.db, user_id)
                body_html = (
                    f"<p>Dear {contact.full_name},</p>"
                    f"<p>{description}</p>"
                    f"<p>Amount: <strong>{currency} {amount:,.2f}</strong></p>"
                )
                html = render_branded_email(
                    branding=branding,
                    subject=f"Payment Link - {currency} {amount:,.2f}",
                    headline="Payment Request",
                    body_html=body_html,
                    cta_text="Pay Now",
                    cta_url=checkout["checkout_url"],
                )
                email_service = EmailService(self.db)
                await email_service.queue_email(
                    to_email=contact.email,
                    subject=f"Payment Link - {currency} {amount:,.2f}",
                    body=html,
                    sent_by_id=user_id,
                    entity_type="payments",
                )
                result["email_sent"] = True
                result["message"] += " Link emailed to contact."

        return result

    async def _send_invoice(self, args: Dict[str, Any], user_id: int) -> Dict[str, Any]:
        """Generate and send an invoice for a completed payment."""
        from src.payments.models import Payment

        result = await self.db.execute(
            select(Payment).where(Payment.id == args["payment_id"])
        )
        payment = result.scalar_one_or_none()
        if not payment:
            return {"error": f"Payment with ID {args['payment_id']} not found."}

        if payment.status != "succeeded":
            return {"error": f"Payment is in '{payment.status}' status, not 'succeeded'."}

        # Find contact email via customer
        email_addr = None
        client_name = "Customer"
        if payment.customer_id:
            from src.payments.models import StripeCustomer
            cust_result = await self.db.execute(
                select(StripeCustomer).where(StripeCustomer.id == payment.customer_id)
            )
            customer = cust_result.scalar_one_or_none()
            if customer:
                email_addr = customer.email
                client_name = customer.name or "Customer"

                if not email_addr and customer.contact_id:
                    contact_result = await self.db.execute(
                        select(Contact).where(Contact.id == customer.contact_id)
                    )
                    contact = contact_result.scalar_one_or_none()
                    if contact:
                        email_addr = contact.email
                        client_name = contact.full_name

        if not email_addr:
            return {"error": "No email address found for this payment's customer."}

        from src.email.branded_templates import TenantBrandingHelper, render_payment_receipt_email
        from src.email.service import EmailService

        branding = await TenantBrandingHelper.get_branding_for_user(self.db, user_id)
        payment_data = {
            "receipt_number": str(payment.id),
            "client_name": client_name,
            "amount": str(float(payment.amount) if payment.amount else "0.00"),
            "currency": payment.currency or "USD",
            "payment_date": payment.created_at.strftime("%Y-%m-%d") if payment.created_at else "",
            "payment_method": payment.payment_method or "Card",
        }
        subject, html_body = render_payment_receipt_email(branding, payment_data)

        email_service = EmailService(self.db)
        await email_service.queue_email(
            to_email=email_addr,
            subject=subject,
            body=html_body,
            sent_by_id=user_id,
            entity_type="payments",
            entity_id=payment.id,
        )

        return {
            "success": True,
            "message": f"Invoice sent to {email_addr} for payment #{payment.id}.",
        }

    async def _send_email_to_contact(self, args: Dict[str, Any], user_id: int) -> Dict[str, Any]:
        """Send a branded email to a contact."""
        contact_result = await self.db.execute(
            select(Contact).where(Contact.id == args["contact_id"])
        )
        contact = contact_result.scalar_one_or_none()
        if not contact:
            return {"error": f"Contact with ID {args['contact_id']} not found."}
        if not contact.email:
            return {"error": f"Contact '{contact.full_name}' has no email address."}

        subject = args["subject"]
        body = args["body"]
        use_branded = args.get("use_branded_template", True)

        from src.email.service import EmailService
        email_service = EmailService(self.db)

        if use_branded:
            from src.email.branded_templates import TenantBrandingHelper, render_branded_email
            branding = await TenantBrandingHelper.get_branding_for_user(self.db, user_id)
            html_body = render_branded_email(
                branding=branding,
                subject=subject,
                headline=subject,
                body_html=body,
            )
        else:
            html_body = body

        await email_service.queue_email(
            to_email=contact.email,
            subject=subject,
            body=html_body,
            sent_by_id=user_id,
            entity_type="contacts",
            entity_id=contact.id,
        )

        return {
            "success": True,
            "message": f"Email sent to {contact.full_name} ({contact.email}).",
        }

    async def _schedule_follow_up_sequence(self, args: Dict[str, Any], user_id: int) -> Dict[str, Any]:
        """Create a multi-step follow-up sequence as scheduled activities."""
        entity_type = args["entity_type"]
        entity_id = args["entity_id"]
        steps = args.get("steps", [])

        if not steps:
            return {"error": "No steps provided for the follow-up sequence."}

        service = ActivityService(self.db)
        created_activities = []

        for step in steps:
            delay_days = step.get("delay_days", 1)
            due = date.today() + timedelta(days=delay_days)

            activity_data = ActivityCreate(
                subject=step.get("subject", "Follow-up"),
                activity_type=step.get("activity_type", "task"),
                entity_type=entity_type,
                entity_id=entity_id,
                due_date=due,
                priority="normal",
                description=step.get("description", ""),
            )
            activity = await service.create(activity_data, user_id)
            created_activities.append({
                "activity_id": activity.id,
                "subject": activity.subject,
                "type": activity.activity_type,
                "due_date": due.isoformat(),
            })

        return {
            "success": True,
            "activities_created": len(created_activities),
            "activities": created_activities,
            "message": f"Scheduled {len(created_activities)} follow-up activities.",
        }

    async def _send_campaign_to_segment(self, args: Dict[str, Any], user_id: int) -> Dict[str, Any]:
        """Trigger sending a campaign to its members."""
        from src.campaigns.models import Campaign

        campaign_result = await self.db.execute(
            select(Campaign).where(Campaign.id == args["campaign_id"])
        )
        campaign = campaign_result.scalar_one_or_none()
        if not campaign:
            return {"error": f"Campaign with ID {args['campaign_id']} not found."}

        # Set campaign status to in_progress
        campaign.status = "in_progress"
        await self.db.flush()

        return {
            "success": True,
            "campaign_id": campaign.id,
            "campaign_name": campaign.name,
            "status": "in_progress",
            "message": f"Campaign '{campaign.name}' execution started.",
        }

    # =========================================================================
    # Audit logging
    # =========================================================================

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
        """Log an AI action execution to the audit log."""
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


def _summarize_result(data: Dict[str, Any]) -> str:
    """Create a brief summary of a function result for the actions_taken list."""
    if "error" in data:
        return f"Error: {data['error']}"
    if "message" in data:
        return data["message"]
    if "count" in data:
        return f"Found {data['count']} results"
    if "report_type" in data:
        return f"{data['report_type']} report generated"
    return "Completed"
