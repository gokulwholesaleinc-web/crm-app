"""AI-powered insights and recommendations."""

from typing import Dict, Any, List
from datetime import datetime, timedelta
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from openai import AsyncOpenAI
from src.config import settings
from src.core.constants import ErrorMessages, EntityNames
from src.leads.models import Lead
from src.opportunities.models import Opportunity, PipelineStage
from src.activities.models import Activity


class InsightsGenerator:
    """Generates AI-powered insights from CRM data."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY) if settings.OPENAI_API_KEY else None

    async def get_lead_insights(self, lead_id: int) -> Dict[str, Any]:
        """Get AI insights for a specific lead."""
        result = await self.db.execute(
            select(Lead).where(Lead.id == lead_id)
        )
        lead = result.scalar_one_or_none()

        if not lead:
            return {"error": ErrorMessages.not_found(EntityNames.LEAD)}

        # Gather data about the lead
        activities = await self.db.execute(
            select(Activity)
            .where(Activity.entity_type == "leads", Activity.entity_id == lead_id)
            .order_by(Activity.created_at.desc())
            .limit(10)
        )
        recent_activities = activities.scalars().all()

        lead_data = {
            "name": lead.full_name,
            "company": lead.company_name,
            "industry": lead.industry,
            "score": lead.score,
            "status": lead.status,
            "budget": lead.budget_amount,
            "requirements": lead.requirements,
            "activity_count": len(recent_activities),
            "recent_activities": [a.activity_type for a in recent_activities],
        }

        if not self.client:
            return {
                "lead_data": lead_data,
                "insights": "AI insights unavailable - OpenAI not configured",
            }

        try:
            response = await self.client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a sales analyst. Analyze this lead data and provide 3-5 actionable insights or recommendations."
                    },
                    {
                        "role": "user",
                        "content": f"Lead data: {lead_data}"
                    }
                ],
                max_tokens=500,
            )

            return {
                "lead_data": lead_data,
                "insights": response.choices[0].message.content,
            }
        except Exception as e:
            return {
                "lead_data": lead_data,
                "insights": f"Error generating insights: {str(e)}",
            }

    async def get_opportunity_insights(self, opportunity_id: int) -> Dict[str, Any]:
        """Get AI insights for a specific opportunity."""
        result = await self.db.execute(
            select(Opportunity)
            .where(Opportunity.id == opportunity_id)
        )
        opp = result.scalar_one_or_none()

        if not opp:
            return {"error": ErrorMessages.not_found(EntityNames.OPPORTUNITY)}

        opp_data = {
            "name": opp.name,
            "amount": opp.amount,
            "stage": opp.pipeline_stage.name if opp.pipeline_stage else None,
            "probability": opp.probability or (opp.pipeline_stage.probability if opp.pipeline_stage else None),
            "expected_close": opp.expected_close_date.isoformat() if opp.expected_close_date else None,
            "days_in_stage": None,  # Could calculate this
        }

        if not self.client:
            return {
                "opportunity_data": opp_data,
                "insights": "AI insights unavailable - OpenAI not configured",
            }

        try:
            response = await self.client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a sales coach. Analyze this opportunity and suggest actions to help close the deal."
                    },
                    {
                        "role": "user",
                        "content": f"Opportunity data: {opp_data}"
                    }
                ],
                max_tokens=500,
            )

            return {
                "opportunity_data": opp_data,
                "insights": response.choices[0].message.content,
            }
        except Exception as e:
            return {
                "opportunity_data": opp_data,
                "insights": f"Error generating insights: {str(e)}",
            }

    async def get_daily_summary(self, user_id: int) -> Dict[str, Any]:
        """Generate a daily summary for the user."""
        today = datetime.now().date()
        yesterday = today - timedelta(days=1)

        # Get today's tasks
        tasks = await self.db.execute(
            select(func.count(Activity.id))
            .where(
                Activity.activity_type == "task",
                Activity.is_completed == False,
                Activity.due_date == today,
            )
        )
        tasks_due = tasks.scalar() or 0

        # Get overdue tasks
        overdue = await self.db.execute(
            select(func.count(Activity.id))
            .where(
                Activity.activity_type == "task",
                Activity.is_completed == False,
                Activity.due_date < today,
            )
        )
        overdue_count = overdue.scalar() or 0

        # New leads today
        new_leads = await self.db.execute(
            select(func.count(Lead.id))
            .where(Lead.created_at >= datetime.combine(today, datetime.min.time()))
        )
        new_leads_count = new_leads.scalar() or 0

        # Hot leads (high score, recent activity)
        hot_leads = await self.db.execute(
            select(func.count(Lead.id))
            .where(Lead.score >= 50, Lead.status.in_(["new", "contacted", "qualified"]))
        )
        hot_leads_count = hot_leads.scalar() or 0

        summary_data = {
            "tasks_due_today": tasks_due,
            "overdue_tasks": overdue_count,
            "new_leads_today": new_leads_count,
            "hot_leads": hot_leads_count,
        }

        if not self.client:
            return {
                "data": summary_data,
                "summary": "AI summary unavailable - OpenAI not configured",
            }

        try:
            response = await self.client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a helpful sales assistant. Generate a brief, friendly daily summary based on these metrics. Keep it under 100 words."
                    },
                    {
                        "role": "user",
                        "content": f"Today's metrics: {summary_data}"
                    }
                ],
                max_tokens=200,
            )

            return {
                "data": summary_data,
                "summary": response.choices[0].message.content,
            }
        except Exception as e:
            return {
                "data": summary_data,
                "summary": f"Error generating summary: {str(e)}",
            }
