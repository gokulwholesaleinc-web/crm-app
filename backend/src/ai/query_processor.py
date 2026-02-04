"""Natural language query processor for AI assistant."""

import json
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from openai import AsyncOpenAI
from src.config import settings
from src.contacts.models import Contact
from src.companies.models import Company
from src.leads.models import Lead
from src.opportunities.models import Opportunity, PipelineStage
from src.activities.models import Activity


class QueryProcessor:
    """
    Processes natural language queries about CRM data.

    Uses GPT-4 to understand intent and generate appropriate responses.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY) if settings.OPENAI_API_KEY else None

    async def process_query(self, query: str, user_id: int) -> Dict[str, Any]:
        """
        Process a natural language query and return response.

        Uses function calling to determine the appropriate action.
        """
        if not self.client:
            return {
                "response": "AI assistant is not configured. Please set OPENAI_API_KEY.",
                "data": None,
            }

        # Define available functions
        functions = [
            {
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
            {
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
            {
                "name": "get_pipeline_summary",
                "description": "Get summary of sales pipeline including total value and deals by stage",
                "parameters": {"type": "object", "properties": {}},
            },
            {
                "name": "get_upcoming_tasks",
                "description": "Get upcoming tasks and activities",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "days": {"type": "integer", "description": "Number of days ahead to look"},
                    },
                },
            },
            {
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
            {
                "name": "get_kpis",
                "description": "Get key performance indicators and metrics",
                "parameters": {"type": "object", "properties": {}},
            },
        ]

        try:
            # First call to determine intent
            response = await self.client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a helpful CRM assistant. Analyze the user's query and call the appropriate function to get data. Then provide a helpful response."
                    },
                    {"role": "user", "content": query}
                ],
                functions=functions,
                function_call="auto",
            )

            message = response.choices[0].message

            # Check if function was called
            if message.function_call:
                func_name = message.function_call.name
                func_args = json.loads(message.function_call.arguments) if message.function_call.arguments else {}

                # Execute the function
                data = await self._execute_function(func_name, func_args, user_id)

                # Get natural language response
                final_response = await self.client.chat.completions.create(
                    model="gpt-4",
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a helpful CRM assistant. Based on the data provided, give a clear and concise response to the user's question."
                        },
                        {"role": "user", "content": query},
                        {"role": "function", "name": func_name, "content": json.dumps(data)},
                    ],
                )

                return {
                    "response": final_response.choices[0].message.content,
                    "data": data,
                    "function_called": func_name,
                }
            else:
                return {
                    "response": message.content,
                    "data": None,
                }

        except Exception as e:
            return {
                "response": f"I encountered an error processing your request: {str(e)}",
                "data": None,
                "error": str(e),
            }

    async def _execute_function(
        self,
        func_name: str,
        args: Dict[str, Any],
        user_id: int,
    ) -> Dict[str, Any]:
        """Execute a function and return results."""

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
        else:
            return {"error": f"Unknown function: {func_name}"}

    async def _search_contacts(
        self,
        search_term: str = None,
        company: str = None,
    ) -> Dict[str, Any]:
        """Search contacts."""
        query = select(Contact).limit(10)

        if search_term:
            query = query.where(
                or_(
                    Contact.first_name.ilike(f"%{search_term}%"),
                    Contact.last_name.ilike(f"%{search_term}%"),
                    Contact.email.ilike(f"%{search_term}%"),
                )
            )

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
            query = query.where(
                or_(
                    Lead.first_name.ilike(f"%{search_term}%"),
                    Lead.last_name.ilike(f"%{search_term}%"),
                    Lead.company_name.ilike(f"%{search_term}%"),
                )
            )

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
        # Contacts count
        contacts = await self.db.execute(select(func.count(Contact.id)))
        contacts_count = contacts.scalar() or 0

        # Open leads
        leads = await self.db.execute(
            select(func.count(Lead.id)).where(
                Lead.status.in_(["new", "contacted", "qualified"])
            )
        )
        leads_count = leads.scalar() or 0

        # Pipeline value
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
