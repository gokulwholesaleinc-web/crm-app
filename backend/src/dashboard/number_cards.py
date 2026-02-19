"""Dashboard number cards data generators."""

import asyncio
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

    def __init__(self, db: AsyncSession, user_id: Optional[int] = None):
        self.db = db
        self.user_id = user_id

    async def get_all_kpis(self, user_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get all KPI data for number cards."""
        # Use passed user_id or fall back to instance user_id
        if user_id and not self.user_id:
            self.user_id = user_id
        kpis = await asyncio.gather(
            self.get_total_contacts(),
            self.get_total_leads(),
            self.get_open_opportunities(),
            self.get_total_revenue(),
            self.get_total_companies(),
            self.get_open_leads(),
            self.get_pipeline_value(),
            self.get_won_this_month(),
            self.get_tasks_due_today(self.user_id),
            self.get_new_leads_this_week(),
            self.get_conversion_rate(),
        )
        return list(kpis)

    async def get_total_contacts(self) -> Dict[str, Any]:
        """Get total active contacts count."""
        filters = [Contact.status == "active"]
        if self.user_id:
            filters.append(Contact.owner_id == self.user_id)
        result = await self.db.execute(
            select(func.count(Contact.id)).where(and_(*filters))
        )
        count = result.scalar() or 0

        # Get last month for comparison
        month_ago = date.today() - timedelta(days=30)
        last_month_filters = [
            Contact.status == "active",
            Contact.created_at < datetime.combine(month_ago, datetime.min.time()),
        ]
        if self.user_id:
            last_month_filters.append(Contact.owner_id == self.user_id)
        last_month_result = await self.db.execute(
            select(func.count(Contact.id)).where(and_(*last_month_filters))
        )
        last_month_count = last_month_result.scalar() or 0
        change = self._calculate_change(count, last_month_count)

        return {
            "id": "total_contacts",
            "label": "Total Contacts",
            "value": count,
            "icon": "users",
            "color": "#3b82f6",
            "change": change,
        }

    async def get_total_leads(self) -> Dict[str, Any]:
        """Get total leads count (all statuses)."""
        query = select(func.count(Lead.id))
        if self.user_id:
            query = query.where(Lead.owner_id == self.user_id)
        result = await self.db.execute(query)
        count = result.scalar() or 0

        # Get last month for comparison
        month_ago = date.today() - timedelta(days=30)
        last_month_filters = [
            Lead.created_at < datetime.combine(month_ago, datetime.min.time()),
        ]
        if self.user_id:
            last_month_filters.append(Lead.owner_id == self.user_id)
        last_month_result = await self.db.execute(
            select(func.count(Lead.id)).where(and_(*last_month_filters))
        )
        last_month_count = last_month_result.scalar() or 0
        change = self._calculate_change(count, last_month_count)

        return {
            "id": "total_leads",
            "label": "Total Leads",
            "value": count,
            "icon": "target",
            "color": "#22c55e",
            "change": change,
        }

    async def get_open_opportunities(self) -> Dict[str, Any]:
        """Get count of open opportunities."""
        filters = [
            PipelineStage.is_won == False,
            PipelineStage.is_lost == False,
        ]
        if self.user_id:
            filters.append(Opportunity.owner_id == self.user_id)
        result = await self.db.execute(
            select(func.count(Opportunity.id))
            .join(PipelineStage)
            .where(and_(*filters))
        )
        count = result.scalar() or 0

        # Get last month for comparison
        month_ago = date.today() - timedelta(days=30)
        last_month_filters = [
            PipelineStage.is_won == False,
            PipelineStage.is_lost == False,
            Opportunity.created_at < datetime.combine(month_ago, datetime.min.time()),
        ]
        if self.user_id:
            last_month_filters.append(Opportunity.owner_id == self.user_id)
        last_month_result = await self.db.execute(
            select(func.count(Opportunity.id))
            .join(PipelineStage)
            .where(and_(*last_month_filters))
        )
        last_month_count = last_month_result.scalar() or 0
        change = self._calculate_change(count, last_month_count)

        return {
            "id": "open_opportunities",
            "label": "Open Opportunities",
            "value": count,
            "icon": "briefcase",
            "color": "#8b5cf6",
            "change": change,
        }

    async def get_total_revenue(self) -> Dict[str, Any]:
        """Get total revenue from won opportunities."""
        filters = [PipelineStage.is_won == True]
        if self.user_id:
            filters.append(Opportunity.owner_id == self.user_id)
        result = await self.db.execute(
            select(func.sum(Opportunity.amount))
            .join(PipelineStage)
            .where(and_(*filters))
        )
        value = result.scalar() or 0

        # Get last month for comparison
        month_ago = date.today() - timedelta(days=30)
        last_month_filters = [
            PipelineStage.is_won == True,
            Opportunity.actual_close_date < month_ago,
        ]
        if self.user_id:
            last_month_filters.append(Opportunity.owner_id == self.user_id)
        last_month_result = await self.db.execute(
            select(func.sum(Opportunity.amount))
            .join(PipelineStage)
            .where(and_(*last_month_filters))
        )
        last_month_value = last_month_result.scalar() or 0
        change = self._calculate_change(float(value), float(last_month_value))

        return {
            "id": "total_revenue",
            "label": "Total Revenue",
            "value": float(value),
            "format": "currency",
            "icon": "dollar-sign",
            "color": "#10b981",
            "change": change,
        }

    def _calculate_change(self, current: float, previous: float) -> Optional[float]:
        """Calculate percentage change between current and previous values."""
        if previous > 0:
            return round(((current - previous) / previous) * 100, 1)
        elif current > 0:
            return 100.0  # New items from zero baseline
        return None

    async def get_total_companies(self) -> Dict[str, Any]:
        """Get total companies count."""
        query = select(func.count(Company.id))
        if self.user_id:
            query = query.where(Company.owner_id == self.user_id)
        result = await self.db.execute(query)
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
        filters = [Lead.status.in_(["new", "contacted", "qualified"])]
        if self.user_id:
            filters.append(Lead.owner_id == self.user_id)
        result = await self.db.execute(
            select(func.count(Lead.id)).where(and_(*filters))
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
        filters = [
            PipelineStage.is_won == False,
            PipelineStage.is_lost == False,
        ]
        if self.user_id:
            filters.append(Opportunity.owner_id == self.user_id)
        result = await self.db.execute(
            select(func.sum(Opportunity.amount))
            .join(PipelineStage)
            .where(and_(*filters))
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

        filters = [
            PipelineStage.is_won == True,
            Opportunity.actual_close_date >= month_start,
        ]
        if self.user_id:
            filters.append(Opportunity.owner_id == self.user_id)
        result = await self.db.execute(
            select(func.sum(Opportunity.amount))
            .join(PipelineStage)
            .where(and_(*filters))
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

        filters = [Lead.created_at >= datetime.combine(week_start, datetime.min.time())]
        if self.user_id:
            filters.append(Lead.owner_id == self.user_id)
        result = await self.db.execute(
            select(func.count(Lead.id)).where(and_(*filters))
        )
        count = result.scalar() or 0

        # Get last week for comparison
        last_week_start = week_start - timedelta(days=7)
        last_week_end = week_start

        last_week_filters = [
            Lead.created_at >= datetime.combine(last_week_start, datetime.min.time()),
            Lead.created_at < datetime.combine(last_week_end, datetime.min.time()),
        ]
        if self.user_id:
            last_week_filters.append(Lead.owner_id == self.user_id)
        last_week_result = await self.db.execute(
            select(func.count(Lead.id)).where(and_(*last_week_filters))
        )
        last_week_count = last_week_result.scalar() or 0
        change = self._calculate_change(count, last_week_count)

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
        total_filters = [Lead.created_at < datetime.now() - timedelta(days=7)]
        if self.user_id:
            total_filters.append(Lead.owner_id == self.user_id)
        total_result = await self.db.execute(
            select(func.count(Lead.id)).where(and_(*total_filters))
        )
        total = total_result.scalar() or 1

        # Converted leads
        converted_filters = [Lead.status == "converted"]
        if self.user_id:
            converted_filters.append(Lead.owner_id == self.user_id)
        converted_result = await self.db.execute(
            select(func.count(Lead.id)).where(and_(*converted_filters))
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
