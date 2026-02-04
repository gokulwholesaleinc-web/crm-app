"""Dashboard number cards data generators."""

from datetime import datetime, timedelta, date
from typing import Dict, Any, List, Optional
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from src.contacts.models import Contact
from src.companies.models import Company
from src.leads.models import Lead
from src.opportunities.models import Opportunity, PipelineStage
from src.activities.models import Activity


class NumberCardGenerator:
    """Generates data for dashboard number cards."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_all_kpis(self, user_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get all KPI data for number cards."""
        kpis = [
            await self.get_total_contacts(),
            await self.get_total_companies(),
            await self.get_open_leads(),
            await self.get_pipeline_value(),
            await self.get_won_this_month(),
            await self.get_tasks_due_today(user_id),
            await self.get_new_leads_this_week(),
            await self.get_conversion_rate(),
        ]
        return kpis

    async def get_total_contacts(self) -> Dict[str, Any]:
        """Get total active contacts count."""
        result = await self.db.execute(
            select(func.count(Contact.id)).where(Contact.status == "active")
        )
        count = result.scalar() or 0

        return {
            "id": "total_contacts",
            "label": "Total Contacts",
            "value": count,
            "icon": "users",
            "color": "#3b82f6",
        }

    async def get_total_companies(self) -> Dict[str, Any]:
        """Get total companies count."""
        result = await self.db.execute(select(func.count(Company.id)))
        count = result.scalar() or 0

        return {
            "id": "total_companies",
            "label": "Companies",
            "value": count,
            "icon": "building",
            "color": "#8b5cf6",
        }

    async def get_open_leads(self) -> Dict[str, Any]:
        """Get count of open leads (not converted or lost)."""
        result = await self.db.execute(
            select(func.count(Lead.id)).where(
                Lead.status.in_(["new", "contacted", "qualified"])
            )
        )
        count = result.scalar() or 0

        return {
            "id": "open_leads",
            "label": "Open Leads",
            "value": count,
            "icon": "target",
            "color": "#22c55e",
        }

    async def get_pipeline_value(self) -> Dict[str, Any]:
        """Get total value of open opportunities."""
        result = await self.db.execute(
            select(func.sum(Opportunity.amount))
            .join(PipelineStage)
            .where(
                and_(
                    PipelineStage.is_won == False,
                    PipelineStage.is_lost == False,
                )
            )
        )
        value = result.scalar() or 0

        return {
            "id": "pipeline_value",
            "label": "Pipeline Value",
            "value": float(value),
            "format": "currency",
            "icon": "chart-line",
            "color": "#f59e0b",
        }

    async def get_won_this_month(self) -> Dict[str, Any]:
        """Get value of opportunities won this month."""
        today = date.today()
        month_start = date(today.year, today.month, 1)

        result = await self.db.execute(
            select(func.sum(Opportunity.amount))
            .join(PipelineStage)
            .where(
                and_(
                    PipelineStage.is_won == True,
                    Opportunity.actual_close_date >= month_start,
                )
            )
        )
        value = result.scalar() or 0

        return {
            "id": "won_this_month",
            "label": "Won This Month",
            "value": float(value),
            "format": "currency",
            "icon": "trophy",
            "color": "#22c55e",
        }

    async def get_tasks_due_today(self, user_id: Optional[int] = None) -> Dict[str, Any]:
        """Get count of tasks due today."""
        today = date.today()

        query = select(func.count(Activity.id)).where(
            and_(
                Activity.activity_type == "task",
                Activity.is_completed == False,
                Activity.due_date == today,
            )
        )

        if user_id:
            from sqlalchemy import or_
            query = query.where(
                or_(
                    Activity.owner_id == user_id,
                    Activity.assigned_to_id == user_id,
                )
            )

        result = await self.db.execute(query)
        count = result.scalar() or 0

        return {
            "id": "tasks_due_today",
            "label": "Tasks Due Today",
            "value": count,
            "icon": "check-circle",
            "color": "#ef4444" if count > 0 else "#22c55e",
        }

    async def get_new_leads_this_week(self) -> Dict[str, Any]:
        """Get count of new leads created this week."""
        today = date.today()
        week_start = today - timedelta(days=today.weekday())

        result = await self.db.execute(
            select(func.count(Lead.id)).where(
                Lead.created_at >= datetime.combine(week_start, datetime.min.time())
            )
        )
        count = result.scalar() or 0

        # Get last week for comparison
        last_week_start = week_start - timedelta(days=7)
        last_week_end = week_start

        last_week_result = await self.db.execute(
            select(func.count(Lead.id)).where(
                and_(
                    Lead.created_at >= datetime.combine(last_week_start, datetime.min.time()),
                    Lead.created_at < datetime.combine(last_week_end, datetime.min.time()),
                )
            )
        )
        last_week_count = last_week_result.scalar() or 0

        # Calculate percentage change
        change = None
        if last_week_count > 0:
            change = round(((count - last_week_count) / last_week_count) * 100, 1)

        return {
            "id": "new_leads_week",
            "label": "New Leads This Week",
            "value": count,
            "icon": "user-plus",
            "color": "#06b6d4",
            "change": change,
        }

    async def get_conversion_rate(self) -> Dict[str, Any]:
        """Get overall lead to opportunity conversion rate."""
        # Total leads (excluding very recent ones)
        total_result = await self.db.execute(
            select(func.count(Lead.id)).where(
                Lead.created_at < datetime.now() - timedelta(days=7)
            )
        )
        total = total_result.scalar() or 1

        # Converted leads
        converted_result = await self.db.execute(
            select(func.count(Lead.id)).where(Lead.status == "converted")
        )
        converted = converted_result.scalar() or 0

        rate = round((converted / total) * 100, 1) if total > 0 else 0

        return {
            "id": "conversion_rate",
            "label": "Conversion Rate",
            "value": rate,
            "format": "percentage",
            "icon": "trending-up",
            "color": "#8b5cf6",
        }
