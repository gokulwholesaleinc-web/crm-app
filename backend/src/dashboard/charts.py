"""Dashboard chart data generators."""

import json
from datetime import datetime, timedelta, date
from typing import Dict, Any, List, Optional
from sqlalchemy import select, func, and_, case
from sqlalchemy.ext.asyncio import AsyncSession
from src.contacts.models import Contact
from src.companies.models import Company
from src.leads.models import Lead
from src.opportunities.models import Opportunity, PipelineStage
from src.activities.models import Activity
from src.campaigns.models import Campaign


class ChartDataGenerator:
    """Generates data for dashboard charts."""

    def __init__(
        self,
        db: AsyncSession,
        user_id: Optional[int] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
    ):
        self.db = db
        self.user_id = user_id
        self.date_from = date_from
        self.date_to = date_to

    def _apply_date_filter(self, filters: list, date_column) -> list:
        """Apply date_from/date_to filters to a filter list."""
        if self.date_from:
            filters.append(date_column >= datetime.combine(self.date_from, datetime.min.time()))
        if self.date_to:
            filters.append(date_column <= datetime.combine(self.date_to, datetime.max.time()))
        return filters

    async def get_pipeline_funnel(self) -> Dict[str, Any]:
        """Get pipeline funnel data."""
        join_conditions = [Opportunity.pipeline_stage_id == PipelineStage.id]
        if self.user_id:
            join_conditions.append(Opportunity.owner_id == self.user_id)
        if self.date_from:
            join_conditions.append(
                Opportunity.created_at >= datetime.combine(self.date_from, datetime.min.time())
            )
        if self.date_to:
            join_conditions.append(
                Opportunity.created_at <= datetime.combine(self.date_to, datetime.max.time())
            )
        query = (
            select(
                PipelineStage.name,
                PipelineStage.color,
                PipelineStage.order,
                func.count(Opportunity.id).label("count"),
                func.sum(Opportunity.amount).label("total_amount"),
            )
            .outerjoin(
                Opportunity,
                and_(*join_conditions),
            )
            .where(PipelineStage.is_active == True)
            .group_by(PipelineStage.id)
            .order_by(PipelineStage.order)
        )
        result = await self.db.execute(query)

        data = []
        for row in result.all():
            data.append({
                "label": row.name,
                "value": row.count or 0,
                "color": row.color,
            })

        return {
            "type": "funnel",
            "title": "Sales Pipeline",
            "data": data,
        }

    async def get_leads_by_status(self) -> Dict[str, Any]:
        """Get leads grouped by status."""
        filters = []
        if self.user_id:
            filters.append(Lead.owner_id == self.user_id)
        self._apply_date_filter(filters, Lead.created_at)
        query = select(
            Lead.status,
            func.count(Lead.id).label("count"),
        )
        if filters:
            query = query.where(and_(*filters))
        query = query.group_by(Lead.status)
        result = await self.db.execute(query)

        data = []
        colors = {
            "new": "#3b82f6",
            "contacted": "#8b5cf6",
            "qualified": "#22c55e",
            "unqualified": "#ef4444",
            "converted": "#06b6d4",
            "lost": "#6b7280",
        }

        for row in result.all():
            data.append({
                "label": row.status.capitalize(),
                "value": row.count,
                "color": colors.get(row.status, "#6b7280"),
            })

        return {
            "type": "pie",
            "title": "Leads by Status",
            "data": data,
        }

    async def get_leads_by_source(self) -> Dict[str, Any]:
        """Get leads grouped by source."""
        from src.leads.models import LeadSource

        join_conditions = [Lead.source_id == LeadSource.id]
        if self.user_id:
            join_conditions.append(Lead.owner_id == self.user_id)
        if self.date_from:
            join_conditions.append(
                Lead.created_at >= datetime.combine(self.date_from, datetime.min.time())
            )
        if self.date_to:
            join_conditions.append(
                Lead.created_at <= datetime.combine(self.date_to, datetime.max.time())
            )
        query = (
            select(
                LeadSource.name,
                func.count(Lead.id).label("count"),
            )
            .outerjoin(
                Lead,
                and_(*join_conditions),
            )
            .group_by(LeadSource.id)
            .order_by(func.count(Lead.id).desc())
            .limit(10)
        )
        result = await self.db.execute(query)

        data = []
        for row in result.all():
            if row.count > 0:
                data.append({
                    "label": row.name,
                    "value": row.count,
                })

        return {
            "type": "bar",
            "title": "Leads by Source",
            "data": data,
        }

    async def get_revenue_trend(self, months: int = 6) -> Dict[str, Any]:
        """Get monthly revenue trend (won opportunities)."""
        today = date.today()
        start_date = date(today.year, today.month, 1) - timedelta(days=30 * (months - 1))

        month_col = func.date_trunc("month", Opportunity.actual_close_date).label("month")
        filters = [
            PipelineStage.is_won == True,
            Opportunity.actual_close_date >= start_date,
        ]
        if self.user_id:
            filters.append(Opportunity.owner_id == self.user_id)
        self._apply_date_filter(filters, Opportunity.created_at)

        result = await self.db.execute(
            select(
                month_col,
                func.sum(Opportunity.amount).label("revenue"),
            )
            .join(PipelineStage)
            .where(and_(*filters))
            .group_by(month_col)
            .order_by(month_col)
        )

        data = []
        for row in result.all():
            if row.month:
                data.append({
                    "label": row.month.strftime("%b %Y"),
                    "value": float(row.revenue or 0),
                })

        return {
            "type": "line",
            "title": "Monthly Revenue",
            "data": data,
        }

    async def get_activities_by_type(self, days: int = 30) -> Dict[str, Any]:
        """Get activities grouped by type for recent period."""
        start_date = datetime.now() - timedelta(days=days)

        filters = [Activity.created_at >= start_date]
        if self.user_id:
            filters.append(Activity.owner_id == self.user_id)
        self._apply_date_filter(filters, Activity.created_at)

        result = await self.db.execute(
            select(
                Activity.activity_type,
                func.count(Activity.id).label("count"),
            )
            .where(and_(*filters))
            .group_by(Activity.activity_type)
        )

        data = []
        colors = {
            "call": "#3b82f6",
            "email": "#22c55e",
            "meeting": "#8b5cf6",
            "task": "#f59e0b",
            "note": "#6b7280",
        }

        for row in result.all():
            data.append({
                "label": row.activity_type.capitalize(),
                "value": row.count,
                "color": colors.get(row.activity_type, "#6b7280"),
            })

        return {
            "type": "pie",
            "title": f"Activities (Last {days} Days)",
            "data": data,
        }

    async def get_new_leads_trend(self, weeks: int = 8) -> Dict[str, Any]:
        """Get weekly new leads trend."""
        start_date = datetime.now() - timedelta(weeks=weeks)

        filters = [Lead.created_at >= start_date]
        if self.user_id:
            filters.append(Lead.owner_id == self.user_id)
        self._apply_date_filter(filters, Lead.created_at)

        week_col = func.date_trunc("week", Lead.created_at).label("week")
        result = await self.db.execute(
            select(
                week_col,
                func.count(Lead.id).label("count"),
            )
            .where(and_(*filters))
            .group_by(week_col)
            .order_by(week_col)
        )

        data = []
        for row in result.all():
            if row.week:
                data.append({
                    "label": f"Week of {row.week.strftime('%b %d')}",
                    "value": row.count,
                })

        return {
            "type": "area",
            "title": "New Leads Trend",
            "data": data,
        }

    async def get_sales_funnel(self) -> Dict[str, Any]:
        """Get sales funnel data: leads by status with conversion rates and avg time."""
        # Define funnel stages in order
        funnel_stages = ["new", "contacted", "qualified", "converted"]
        colors = {
            "new": "#3b82f6",
            "contacted": "#8b5cf6",
            "qualified": "#22c55e",
            "converted": "#06b6d4",
        }

        # Get counts per status
        filters = [Lead.status.in_(funnel_stages)]
        if self.user_id:
            filters.append(Lead.owner_id == self.user_id)
        self._apply_date_filter(filters, Lead.created_at)

        result = await self.db.execute(
            select(
                Lead.status,
                func.count(Lead.id).label("count"),
            )
            .where(and_(*filters))
            .group_by(Lead.status)
        )
        status_counts = {row.status: row.count for row in result.all()}

        stages = []
        for stage in funnel_stages:
            stages.append({
                "stage": stage,
                "count": status_counts.get(stage, 0),
                "color": colors.get(stage),
            })

        # Calculate conversion rates between consecutive stages
        conversions = []
        for i in range(len(funnel_stages) - 1):
            from_stage = funnel_stages[i]
            to_stage = funnel_stages[i + 1]
            from_count = status_counts.get(from_stage, 0)
            to_count = status_counts.get(to_stage, 0)
            rate = (to_count / from_count * 100) if from_count > 0 else 0
            conversions.append({
                "from_stage": from_stage,
                "to_stage": to_stage,
                "rate": round(rate, 1),
            })

        # Average days in each stage (approximate via created_at to updated_at)
        avg_filters = [Lead.status.in_(funnel_stages)]
        if self.user_id:
            avg_filters.append(Lead.owner_id == self.user_id)
        self._apply_date_filter(avg_filters, Lead.created_at)
        avg_result = await self.db.execute(
            select(
                Lead.status,
                func.avg(
                    func.extract("epoch", Lead.updated_at - Lead.created_at) / 86400
                ).label("avg_days"),
            )
            .where(and_(*avg_filters))
            .group_by(Lead.status)
        )
        avg_days = {}
        for row in avg_result.all():
            avg_days[row.status] = round(float(row.avg_days), 1) if row.avg_days else None

        return {
            "stages": stages,
            "conversions": conversions,
            "avg_days_in_stage": avg_days,
        }

    async def get_conversion_rates(self) -> Dict[str, Any]:
        """Get conversion rates across different stages."""
        import asyncio

        # Build base filters for date range
        total_filters = []
        if self.user_id:
            total_filters.append(Lead.owner_id == self.user_id)
        self._apply_date_filter(total_filters, Lead.created_at)

        converted_filters = [Lead.status == "converted"]
        if self.user_id:
            converted_filters.append(Lead.owner_id == self.user_id)
        self._apply_date_filter(converted_filters, Lead.created_at)

        won_filters = [PipelineStage.is_won == True]
        if self.user_id:
            won_filters.append(Opportunity.owner_id == self.user_id)
        self._apply_date_filter(won_filters, Opportunity.created_at)

        # Build queries
        total_query = select(func.count(Lead.id))
        if total_filters:
            total_query = total_query.where(and_(*total_filters))

        converted_query = select(func.count(Lead.id)).where(and_(*converted_filters))

        won_query = (
            select(func.count(Opportunity.id))
            .join(PipelineStage)
            .where(and_(*won_filters))
        )

        # Execute all 3 queries in parallel
        total_leads, converted, won = await asyncio.gather(
            self.db.execute(total_query),
            self.db.execute(converted_query),
            self.db.execute(won_query),
        )

        total = total_leads.scalar() or 1
        converted_count = converted.scalar() or 0
        won_count = won.scalar() or 0

        data = [
            {
                "label": "Lead → Opportunity",
                "value": round((converted_count / total) * 100, 1) if total > 0 else 0,
            },
            {
                "label": "Opportunity → Won",
                "value": round((won_count / converted_count) * 100, 1) if converted_count > 0 else 0,
            },
        ]

        return {
            "type": "bar",
            "title": "Conversion Rates (%)",
            "data": data,
        }
