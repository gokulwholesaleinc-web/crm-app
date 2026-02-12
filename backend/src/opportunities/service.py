"""Opportunity service layer."""

from typing import Optional, List, Tuple, Any, Dict
from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload
from src.opportunities.models import Opportunity, PipelineStage
from src.core.filtering import apply_filters_to_query, build_token_search
from src.opportunities.schemas import (
    OpportunityCreate,
    OpportunityUpdate,
    PipelineStageCreate,
    PipelineStageUpdate,
)
from src.core.base_service import CRUDService, BaseService, TaggableServiceMixin
from src.core.constants import ENTITY_TYPE_OPPORTUNITIES, DEFAULT_PAGE_SIZE


class OpportunityService(
    CRUDService[Opportunity, OpportunityCreate, OpportunityUpdate],
    TaggableServiceMixin,
):
    """Service for Opportunity CRUD operations with tag support."""

    model = Opportunity
    entity_type = ENTITY_TYPE_OPPORTUNITIES

    def _get_eager_load_options(self):
        """Load pipeline stage, contact, and company relations."""
        return [
            selectinload(Opportunity.pipeline_stage),
            selectinload(Opportunity.contact),
            selectinload(Opportunity.company),
        ]

    async def get_list(
        self,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
        search: Optional[str] = None,
        pipeline_stage_id: Optional[int] = None,
        contact_id: Optional[int] = None,
        company_id: Optional[int] = None,
        owner_id: Optional[int] = None,
        tag_ids: Optional[List[int]] = None,
        filters: Optional[Dict[str, Any]] = None,
        shared_entity_ids: Optional[List[int]] = None,
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

        if filters:
            query = apply_filters_to_query(query, Opportunity, filters)

        if search:
            search_condition = build_token_search(search, Opportunity.name)
            if search_condition is not None:
                query = query.where(search_condition)

        if pipeline_stage_id:
            query = query.where(Opportunity.pipeline_stage_id == pipeline_stage_id)

        if contact_id:
            query = query.where(Opportunity.contact_id == contact_id)

        if company_id:
            query = query.where(Opportunity.company_id == company_id)

        if owner_id:
            if shared_entity_ids:
                query = query.where(or_(Opportunity.owner_id == owner_id, Opportunity.id.in_(shared_entity_ids)))
            else:
                query = query.where(Opportunity.owner_id == owner_id)

        if tag_ids:
            query = await self._filter_by_tags(query, tag_ids)

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
        opportunity = await super().create(data, user_id)

        if data.tag_ids:
            await self.update_tags(opportunity.id, data.tag_ids)
            await self.db.refresh(opportunity)

        return opportunity

    async def update(self, opportunity: Opportunity, data: OpportunityUpdate, user_id: int) -> Opportunity:
        """Update an opportunity."""
        opportunity = await super().update(opportunity, data, user_id)

        if data.tag_ids is not None:
            await self.update_tags(opportunity.id, data.tag_ids)
            await self.db.refresh(opportunity)

        return opportunity

    async def delete(self, opportunity: Opportunity) -> None:
        """Delete an opportunity."""
        await self.clear_tags(opportunity.id)
        await super().delete(opportunity)



class PipelineStageService(BaseService[PipelineStage]):
    """Service for PipelineStage operations."""

    model = PipelineStage

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
