"""Opportunity service layer."""

from typing import Optional, List, Tuple
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from src.opportunities.models import Opportunity, PipelineStage
from src.opportunities.schemas import (
    OpportunityCreate,
    OpportunityUpdate,
    PipelineStageCreate,
    PipelineStageUpdate,
)
from src.core.models import Tag, EntityTag


class OpportunityService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, opportunity_id: int) -> Optional[Opportunity]:
        """Get opportunity by ID with related data."""
        result = await self.db.execute(
            select(Opportunity)
            .where(Opportunity.id == opportunity_id)
            .options(
                selectinload(Opportunity.pipeline_stage),
                selectinload(Opportunity.contact),
                selectinload(Opportunity.company),
            )
        )
        return result.scalar_one_or_none()

    async def get_list(
        self,
        page: int = 1,
        page_size: int = 20,
        search: Optional[str] = None,
        pipeline_stage_id: Optional[int] = None,
        contact_id: Optional[int] = None,
        company_id: Optional[int] = None,
        owner_id: Optional[int] = None,
        tag_ids: Optional[List[int]] = None,
    ) -> Tuple[List[Opportunity], int]:
        """Get paginated list of opportunities with filters."""
        query = (
            select(Opportunity)
            .options(
                selectinload(Opportunity.pipeline_stage),
                selectinload(Opportunity.contact),
                selectinload(Opportunity.company),
            )
        )

        if search:
            query = query.where(Opportunity.name.ilike(f"%{search}%"))

        if pipeline_stage_id:
            query = query.where(Opportunity.pipeline_stage_id == pipeline_stage_id)

        if contact_id:
            query = query.where(Opportunity.contact_id == contact_id)

        if company_id:
            query = query.where(Opportunity.company_id == company_id)

        if owner_id:
            query = query.where(Opportunity.owner_id == owner_id)

        if tag_ids:
            tag_subquery = (
                select(EntityTag.entity_id)
                .where(EntityTag.entity_type == "opportunities")
                .where(EntityTag.tag_id.in_(tag_ids))
                .group_by(EntityTag.entity_id)
                .having(func.count(EntityTag.tag_id) == len(tag_ids))
            )
            query = query.where(Opportunity.id.in_(tag_subquery))

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar()

        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(Opportunity.created_at.desc())

        result = await self.db.execute(query)
        opportunities = list(result.scalars().all())

        return opportunities, total

    async def create(self, data: OpportunityCreate, user_id: int) -> Opportunity:
        """Create a new opportunity."""
        opp_data = data.model_dump(exclude={"tag_ids"})
        opportunity = Opportunity(**opp_data, created_by_id=user_id)
        self.db.add(opportunity)
        await self.db.flush()

        if data.tag_ids:
            await self._update_tags(opportunity.id, data.tag_ids)

        await self.db.refresh(opportunity)
        return opportunity

    async def update(self, opportunity: Opportunity, data: OpportunityUpdate, user_id: int) -> Opportunity:
        """Update an opportunity."""
        update_data = data.model_dump(exclude={"tag_ids"}, exclude_unset=True)
        for field, value in update_data.items():
            setattr(opportunity, field, value)
        opportunity.updated_by_id = user_id
        await self.db.flush()

        if data.tag_ids is not None:
            await self._update_tags(opportunity.id, data.tag_ids)

        await self.db.refresh(opportunity)
        return opportunity

    async def delete(self, opportunity: Opportunity) -> None:
        """Delete an opportunity."""
        await self.db.execute(
            EntityTag.__table__.delete().where(
                EntityTag.entity_type == "opportunities",
                EntityTag.entity_id == opportunity.id,
            )
        )
        await self.db.delete(opportunity)
        await self.db.flush()

    async def _update_tags(self, opportunity_id: int, tag_ids: List[int]) -> None:
        """Update tags for an opportunity."""
        await self.db.execute(
            EntityTag.__table__.delete().where(
                EntityTag.entity_type == "opportunities",
                EntityTag.entity_id == opportunity_id,
            )
        )

        for tag_id in tag_ids:
            entity_tag = EntityTag(
                entity_type="opportunities",
                entity_id=opportunity_id,
                tag_id=tag_id,
            )
            self.db.add(entity_tag)
        await self.db.flush()

    async def get_opportunity_tags(self, opportunity_id: int) -> List[Tag]:
        """Get tags for an opportunity."""
        result = await self.db.execute(
            select(Tag)
            .join(EntityTag)
            .where(EntityTag.entity_type == "opportunities")
            .where(EntityTag.entity_id == opportunity_id)
        )
        return list(result.scalars().all())


class PipelineStageService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, stage_id: int) -> Optional[PipelineStage]:
        """Get pipeline stage by ID."""
        result = await self.db.execute(
            select(PipelineStage).where(PipelineStage.id == stage_id)
        )
        return result.scalar_one_or_none()

    async def get_all(self, active_only: bool = True) -> List[PipelineStage]:
        """Get all pipeline stages ordered by order field."""
        query = select(PipelineStage)
        if active_only:
            query = query.where(PipelineStage.is_active == True)
        query = query.order_by(PipelineStage.order)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def create(self, data: PipelineStageCreate) -> PipelineStage:
        """Create a new pipeline stage."""
        stage = PipelineStage(**data.model_dump())
        self.db.add(stage)
        await self.db.flush()
        await self.db.refresh(stage)
        return stage

    async def update(self, stage: PipelineStage, data: PipelineStageUpdate) -> PipelineStage:
        """Update a pipeline stage."""
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(stage, field, value)
        await self.db.flush()
        await self.db.refresh(stage)
        return stage

    async def delete(self, stage: PipelineStage) -> None:
        """Delete a pipeline stage."""
        await self.db.delete(stage)
        await self.db.flush()

    async def reorder(self, stage_orders: List[dict]) -> List[PipelineStage]:
        """Reorder pipeline stages. stage_orders: [{id: int, order: int}, ...]"""
        for item in stage_orders:
            result = await self.db.execute(
                select(PipelineStage).where(PipelineStage.id == item["id"])
            )
            stage = result.scalar_one_or_none()
            if stage:
                stage.order = item["order"]
        await self.db.flush()
        return await self.get_all()
