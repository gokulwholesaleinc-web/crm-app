"""Revenue forecasting utilities."""

from datetime import date, timedelta
from typing import Dict, List, Any
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from src.opportunities.models import Opportunity, PipelineStage


class RevenueForecast:
    """Revenue forecasting based on pipeline data."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_forecast(
        self,
        months_ahead: int = 6,
        owner_id: int = None,
    ) -> Dict[str, Any]:
        """
        Generate revenue forecast for the specified period.

        Returns monthly breakdown with:
        - Expected revenue (weighted by probability)
        - Best case (all opportunities close)
        - Commit (only high-probability opportunities)
        """
        today = date.today()
        forecast_periods = []

        for i in range(months_ahead):
            # Calculate month start/end
            month_start = date(
                today.year + (today.month + i - 1) // 12,
                (today.month + i - 1) % 12 + 1,
                1
            )
            if i + 1 < months_ahead:
                next_month = date(
                    today.year + (today.month + i) // 12,
                    (today.month + i) % 12 + 1,
                    1
                )
            else:
                # Last month in forecast
                if month_start.month == 12:
                    next_month = date(month_start.year + 1, 1, 1)
                else:
                    next_month = date(month_start.year, month_start.month + 1, 1)

            month_end = next_month - timedelta(days=1)

            # Query opportunities expected to close in this period
            query = (
                select(Opportunity)
                .join(PipelineStage)
                .where(
                    and_(
                        Opportunity.expected_close_date >= month_start,
                        Opportunity.expected_close_date <= month_end,
                        PipelineStage.is_won == False,
                        PipelineStage.is_lost == False,
                    )
                )
            )
            if owner_id:
                query = query.where(Opportunity.owner_id == owner_id)

            result = await self.db.execute(query)
            opportunities = list(result.scalars().all())

            # Calculate metrics
            best_case = sum(opp.amount or 0 for opp in opportunities)
            weighted = sum(opp.weighted_amount or 0 for opp in opportunities)
            commit = sum(
                opp.amount or 0
                for opp in opportunities
                if (opp.probability or opp.pipeline_stage.probability) >= 75
            )

            forecast_periods.append({
                "month": month_start.strftime("%Y-%m"),
                "month_label": month_start.strftime("%B %Y"),
                "best_case": best_case,
                "weighted": weighted,
                "commit": commit,
                "opportunity_count": len(opportunities),
            })

        # Calculate totals
        total_best_case = sum(p["best_case"] for p in forecast_periods)
        total_weighted = sum(p["weighted"] for p in forecast_periods)
        total_commit = sum(p["commit"] for p in forecast_periods)

        return {
            "periods": forecast_periods,
            "totals": {
                "best_case": total_best_case,
                "weighted": total_weighted,
                "commit": total_commit,
            },
            "currency": "USD",  # Could be made configurable
        }

    async def get_pipeline_summary(self, owner_id: int = None) -> Dict[str, Any]:
        """Get summary of current pipeline value."""
        # Query all open opportunities
        query = (
            select(Opportunity)
            .join(PipelineStage)
            .where(
                and_(
                    PipelineStage.is_won == False,
                    PipelineStage.is_lost == False,
                )
            )
        )
        if owner_id:
            query = query.where(Opportunity.owner_id == owner_id)

        result = await self.db.execute(query)
        opportunities = list(result.scalars().all())

        total_value = sum(opp.amount or 0 for opp in opportunities)
        weighted_value = sum(opp.weighted_amount or 0 for opp in opportunities)

        # Group by stage
        stage_breakdown = {}
        for opp in opportunities:
            stage_name = opp.pipeline_stage.name
            if stage_name not in stage_breakdown:
                stage_breakdown[stage_name] = {
                    "count": 0,
                    "value": 0,
                    "weighted": 0,
                }
            stage_breakdown[stage_name]["count"] += 1
            stage_breakdown[stage_name]["value"] += opp.amount or 0
            stage_breakdown[stage_name]["weighted"] += opp.weighted_amount or 0

        return {
            "total_opportunities": len(opportunities),
            "total_value": total_value,
            "weighted_value": weighted_value,
            "currency": "USD",
            "by_stage": stage_breakdown,
        }
