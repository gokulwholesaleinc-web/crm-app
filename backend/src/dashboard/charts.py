"""Dashboard chart data generators."""

import json
from datetime import datetime, timedelta, date
from typing import Dict, Any, List, Optional
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from src.contacts.models import Contact
from src.companies.models import Company
from src.leads.models import Lead
from src.opportunities.models import Opportunity, PipelineStage
from src.activities.models import Activity
from src.campaigns.models import Campaign


class ChartDataGenerator:
    """Generates data for dashboard charts."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_pipeline_funnel(self) -> Dict[str, Any]:
        """Get pipeline funnel data."""
        result = await self.db.execute(
            select(
                PipelineStage.name,
                PipelineStage.color,
                PipelineStage.order,
                func.count(Opportunity.id).label("count"),
                func.sum(Opportunity.amount).label("total_amount"),
            )
            .outerjoin(Opportunity)
            .where(PipelineStage.is_active == True)
            .group_by(PipelineStage.id)
            .order_by(PipelineStage.order)
        )

        data = []
        for row in result.all():
            data.append({
                "stage": row.name,
                "color": row.color,
                "count": row.count or 0,
                "amount": float(row.total_amount or 0),
            })

        return {
            "type": "funnel",
            "title": "Sales Pipeline",
            "data": data,
        }

    async def get_leads_by_status(self) -> Dict[str, Any]:
        """Get leads grouped by status."""
        result = await self.db.execute(
            select(
                Lead.status,
                func.count(Lead.id).label("count"),
            )
            .group_by(Lead.status)
        )

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

        result = await self.db.execute(
            select(
                LeadSource.name,
                func.count(Lead.id).label("count"),
            )
            .outerjoin(Lead)
            .group_by(LeadSource.id)
            .order_by(func.count(Lead.id).desc())
            .limit(10)
        )

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
        result = await self.db.execute(
            select(
                month_col,
                func.sum(Opportunity.amount).label("revenue"),
            )
            .join(PipelineStage)
            .where(
                and_(
                    PipelineStage.is_won == True,
                    Opportunity.actual_close_date >= start_date,
                )
            )
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

        result = await self.db.execute(
            select(
                Activity.activity_type,
                func.count(Activity.id).label("count"),
            )
            .where(Activity.created_at >= start_date)
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

        week_col = func.date_trunc("week", Lead.created_at).label("week")
        result = await self.db.execute(
            select(
                week_col,
                func.count(Lead.id).label("count"),
            )
            .where(Lead.created_at >= start_date)
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

    async def get_conversion_rates(self) -> Dict[str, Any]:
        """Get conversion rates across different stages."""
        # Total leads
        total_leads = await self.db.execute(select(func.count(Lead.id)))
        total = total_leads.scalar() or 1

        # Converted leads
        converted = await self.db.execute(
            select(func.count(Lead.id)).where(Lead.status == "converted")
        )
        converted_count = converted.scalar() or 0

        # Won opportunities
        won = await self.db.execute(
            select(func.count(Opportunity.id))
            .join(PipelineStage)
            .where(PipelineStage.is_won == True)
        )
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
