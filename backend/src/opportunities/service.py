"""Opportunity service layer."""

from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from src.core.base_service import BaseService, CRUDService, TaggableServiceMixin
from src.core.constants import DEFAULT_PAGE_SIZE, ENTITY_TYPE_OPPORTUNITIES
from src.core.filtering import apply_filters_to_query, build_token_search
from src.opportunities.models import Opportunity, PipelineStage
from src.opportunities.schemas import (
    OpportunityCreate,
    OpportunityUpdate,
    PipelineStageCreate,
    PipelineStageUpdate,
)


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
        search: str | None = None,
        pipeline_stage_id: int | None = None,
        contact_id: int | None = None,
        company_id: int | None = None,
        owner_id: int | None = None,
        tag_ids: list[int] | None = None,
        filters: dict[str, Any] | None = None,
        shared_entity_ids: list[int] | None = None,
        assignee_entity_ids: list[int] | None = None,
    ) -> tuple[list[Opportunity], int]:
        """Get paginated list of opportunities with filters.

        When ``owner_id`` is set, the result includes records owned by that
        user plus any records in ``shared_entity_ids`` or
        ``assignee_entity_ids``. ``assignee_entity_ids`` is a distinct
        parameter so callers that bypass DataScope can OR in just the
        assignee shares without rebuilding the full shared-entity map.
        """
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

        if owner_id is not None:
            or_clauses = [Opportunity.owner_id == owner_id]
            if shared_entity_ids:
                or_clauses.append(Opportunity.id.in_(shared_entity_ids))
            if assignee_entity_ids:
                or_clauses.append(Opportunity.id.in_(assignee_entity_ids))
            query = query.where(or_(*or_clauses))
        else:
            # No owner filter — fall back to base helper which is a no-op when
            # owner_id is None (admin / manager "see all" path).
            query = self.apply_owner_filter(query, owner_id, shared_entity_ids)

        if tag_ids:
            query = await self._filter_by_tags(query, tag_ids)

        return await self.paginate_query(query, page, page_size)

    async def get_assignee_entity_ids(self, user_id: int) -> list[int]:
        """Return opportunity IDs where this user holds an 'assignee' share."""
        from src.core.models import EntityShare

        result = await self.db.execute(
            select(EntityShare.entity_id).where(
                EntityShare.shared_with_user_id == user_id,
                EntityShare.entity_type == ENTITY_TYPE_OPPORTUNITIES,
                EntityShare.permission_level == "assignee",
            )
        )
        return list(result.scalars().all())



class PipelineStageService(BaseService[PipelineStage]):
    """Service for PipelineStage operations."""

    model = PipelineStage

    async def get_all(self, active_only: bool = True, pipeline_type: str | None = None) -> list[PipelineStage]:
        """Get all pipeline stages ordered by order field, optionally filtered by pipeline_type."""
        query = select(PipelineStage)
        if pipeline_type is not None:
            query = query.where(PipelineStage.pipeline_type == pipeline_type)
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

    async def reorder(self, stage_orders: list[dict]) -> list[PipelineStage]:
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
