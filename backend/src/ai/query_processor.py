"""Natural language query processor for AI assistant."""

import json
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta, date
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
]


SYSTEM_PROMPT_BASE = (
    "You are a helpful CRM assistant. You can search data, create leads, "
    "schedule activities, update statuses, add notes, generate reports, "
    "search quotes and proposals, view payment summaries, get campaign stats, "
    "and provide deal coaching. You can also remember user preferences. "
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
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY) if settings.OPENAI_API_KEY else None

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
