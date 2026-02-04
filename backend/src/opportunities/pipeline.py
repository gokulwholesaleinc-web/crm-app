"""Pipeline management utilities."""

from typing import List, Dict, Any
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from src.opportunities.models import Opportunity, PipelineStage


class PipelineManager:
    """Manages pipeline stages and Kanban view data."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_kanban_data(self, owner_id: int = None) -> List[Dict[str, Any]]:
        """
        Get pipeline data formatted for Kanban board.

        Returns list of stages with their opportunities.
        """
        # Get all active stages ordered
        stages_result = await self.db.execute(
            select(PipelineStage)
            .where(PipelineStage.is_active == True)
            .order_by(PipelineStage.order)
        )
        stages = stages_result.scalars().all()

        kanban_data = []

        for stage in stages:
            # Get opportunities for this stage
            opp_query = (
                select(Opportunity)
                .where(Opportunity.pipeline_stage_id == stage.id)
            )
            if owner_id:
                opp_query = opp_query.where(Opportunity.owner_id == owner_id)

            opp_query = opp_query.order_by(Opportunity.expected_close_date.asc().nullslast())

            opp_result = await self.db.execute(opp_query)
            opportunities = opp_result.scalars().all()

            stage_data = {
                "stage_id": stage.id,
                "stage_name": stage.name,
                "color": stage.color,
                "probability": stage.probability,
                "is_won": stage.is_won,
                "is_lost": stage.is_lost,
                "opportunities": [
                    {
                        "id": opp.id,
                        "name": opp.name,
                        "amount": opp.amount,
                        "currency": opp.currency,
                        "weighted_amount": opp.weighted_amount,
                        "expected_close_date": opp.expected_close_date.isoformat() if opp.expected_close_date else None,
                        "contact_name": opp.contact.full_name if opp.contact else None,
                        "company_name": opp.company.name if opp.company else None,
                        "owner_id": opp.owner_id,
                    }
                    for opp in opportunities
                ],
                "total_amount": sum(opp.amount or 0 for opp in opportunities),
                "total_weighted": sum(opp.weighted_amount or 0 for opp in opportunities),
                "count": len(opportunities),
            }
            kanban_data.append(stage_data)

        return kanban_data

    async def move_opportunity(
        self,
        opportunity_id: int,
        new_stage_id: int,
    ) -> Opportunity:
        """Move an opportunity to a new pipeline stage."""
        result = await self.db.execute(
            select(Opportunity).where(Opportunity.id == opportunity_id)
        )
        opportunity = result.scalar_one_or_none()

        if not opportunity:
            raise ValueError(f"Opportunity {opportunity_id} not found")

        # Verify stage exists
        stage_result = await self.db.execute(
            select(PipelineStage).where(PipelineStage.id == new_stage_id)
        )
        stage = stage_result.scalar_one_or_none()

        if not stage:
            raise ValueError(f"Pipeline stage {new_stage_id} not found")

        opportunity.pipeline_stage_id = new_stage_id

        # If moving to won/lost stage, update accordingly
        if stage.is_won or stage.is_lost:
            from datetime import date
            opportunity.actual_close_date = date.today()

        await self.db.flush()
        await self.db.refresh(opportunity)

        return opportunity
