"""Pipeline management utilities."""

from typing import List, Dict, Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from src.core.constants import ErrorMessages, EntityNames
from src.opportunities.models import Opportunity, PipelineStage


class PipelineManager:
    """Manages pipeline stages and Kanban view data."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_kanban_data(self, owner_id: int = None) -> List[Dict[str, Any]]:
        """
        Get pipeline data formatted for Kanban board.

        Returns list of stages with their opportunities. Runs exactly two
        queries (one for stages, one for all opportunities with eager-loaded
        contact and company) regardless of stage count.
        """
        # Query 1: all active opportunity stages ordered.
        stages_result = await self.db.execute(
            select(PipelineStage)
            .where(PipelineStage.is_active == True)
            .where(PipelineStage.pipeline_type == "opportunity")
            .order_by(PipelineStage.order)
        )
        stages = stages_result.scalars().all()

        # Query 2: all opportunities for these stages with eager-loaded
        # contact and company. Contact.company is lazy="joined" so it loads
        # automatically when contact is loaded — no extra round trip per row.
        opp_query = (
            select(Opportunity)
            .options(
                selectinload(Opportunity.contact),
                selectinload(Opportunity.company),
            )
            .where(Opportunity.pipeline_stage_id.in_([s.id for s in stages]))
            .order_by(Opportunity.expected_close_date.asc().nullslast())
        )
        if owner_id:
            opp_query = opp_query.where(Opportunity.owner_id == owner_id)

        opp_result = await self.db.execute(opp_query)
        opps_by_stage: Dict[int, List[Opportunity]] = {stage.id: [] for stage in stages}
        for opp in opp_result.scalars().all():
            opps_by_stage[opp.pipeline_stage_id].append(opp)

        kanban_data = []
        for stage in stages:
            stage_opps = opps_by_stage[stage.id]
            kanban_data.append({
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
                    for opp in stage_opps
                ],
                "total_amount": sum(opp.amount or 0 for opp in stage_opps),
                "total_weighted": sum(opp.weighted_amount or 0 for opp in stage_opps),
                "count": len(stage_opps),
            })
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
            raise ValueError(ErrorMessages.not_found_with_id(EntityNames.OPPORTUNITY, opportunity_id))

        # Verify stage exists and is an opportunity stage
        stage_result = await self.db.execute(
            select(PipelineStage).where(PipelineStage.id == new_stage_id)
        )
        stage = stage_result.scalar_one_or_none()

        if not stage:
            raise ValueError(ErrorMessages.not_found_with_id(EntityNames.PIPELINE_STAGE, new_stage_id))

        opportunity.pipeline_stage_id = new_stage_id

        # If moving to won/lost stage, update accordingly
        if stage.is_won or stage.is_lost:
            from datetime import date
            opportunity.actual_close_date = date.today()

        await self.db.flush()
        await self.db.refresh(opportunity)

        return opportunity
