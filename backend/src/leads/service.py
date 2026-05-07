"""Lead service layer."""

import logging
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from src.core.base_service import CRUDService, TaggableServiceMixin
from src.core.constants import DEFAULT_PAGE_SIZE, ENTITY_TYPE_LEADS
from src.core.filtering import apply_filters_to_query, build_token_search
from src.core.sorting import build_order_clauses
from src.leads.models import Lead, LeadSource
from src.leads.schemas import LeadCreate, LeadSourceCreate, LeadSourceUpdate, LeadUpdate
from src.leads.scoring import calculate_lead_score
from src.opportunities.models import PipelineStage

logger = logging.getLogger(__name__)


# `name` sorts by (last_name, first_name) — Lead.full_name is a Python property
# (first/last with company_name fallback), not a column. Surname-first matches
# the alphabetical convention users expect on a leads list.
LEAD_SORTABLE_FIELDS: dict[str, Any] = {
    "name": (Lead.last_name, Lead.first_name),
    "status": Lead.status,
    "score": Lead.score,
    "created_at": Lead.created_at,
}


class LeadValidationError(ValueError):
    """Domain-specific validation error for the lead service.

    Subclassed so the router can surface the message as a 400 without
    swallowing unrelated `ValueError`s from filter parsing, numeric
    coercion, or third-party libraries.
    """


class LeadService(
    CRUDService[Lead, LeadCreate, LeadUpdate],
    TaggableServiceMixin,
):
    """Service for Lead CRUD operations with tag support and auto-scoring."""

    model = Lead
    entity_type = ENTITY_TYPE_LEADS

    def _get_eager_load_options(self):
        """Load source relation."""
        return [selectinload(Lead.source)]

    async def get_list(
        self,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
        search: str | None = None,
        status: str | None = None,
        source_id: int | None = None,
        owner_id: int | None = None,
        min_score: int | None = None,
        tag_ids: list[int] | None = None,
        filters: dict[str, Any] | None = None,
        shared_entity_ids: list[int] | None = None,
        order_by: str | None = None,
        order_dir: str | None = None,
    ) -> tuple[list[Lead], int]:
        """Get paginated list of leads with filters."""
        query = select(Lead).options(selectinload(Lead.source))

        if filters:
            query = apply_filters_to_query(query, Lead, filters)

        if search:
            search_condition = build_token_search(search, Lead.first_name, Lead.last_name, Lead.email, Lead.company_name)
            if search_condition is not None:
                query = query.where(search_condition)

        # Hide dedup-merged tombstones by default. Callers that want to
        # inspect merged rows can still pass ``status="merged"``.
        if status:
            query = query.where(Lead.status == status)
        else:
            query = query.where(Lead.status != "merged")

        if source_id:
            query = query.where(Lead.source_id == source_id)

        query = self.apply_owner_filter(query, owner_id, shared_entity_ids)

        if min_score is not None:
            query = query.where(Lead.score >= min_score)

        if tag_ids:
            query = await self._filter_by_tags(query, tag_ids)

        order_clauses = build_order_clauses(
            LEAD_SORTABLE_FIELDS,
            order_by,
            order_dir,
            default=[Lead.score.desc(), Lead.id.desc()],
        )
        return await self.paginate_query(query, page, page_size, order_by=order_clauses)

    async def create(self, data: LeadCreate, user_id: int) -> Lead:
        """Create a new lead with auto-scoring.

        Auto-assigns the first active lead-typed pipeline stage when none
        was provided so the new row shows up on the unified `/pipeline`
        kanban instead of being invisible (every column reading "0").
        Refuses status='converted' on this path too — same reasoning as
        update; manual setting bypasses the Convert flow's contact +
        opportunity creation.
        """
        if data.status == "converted":
            raise LeadValidationError(
                "Cannot create a lead with status='converted' — use the "
                "Convert action on a qualified lead so the contact and "
                "opportunity are created.",
            )
        lead = await super().create(data, user_id)
        if lead.pipeline_stage_id is None:
            stage_id = await self._first_lead_stage_id()
            if stage_id is not None:
                lead.pipeline_stage_id = stage_id
                await self.db.flush()
            else:
                logger.warning(
                    "Lead %s created without a pipeline_stage_id — no "
                    "active 'lead' PipelineStage seeded. Run "
                    "POST /api/leads/backfill-pipeline-stages once seeds "
                    "exist to backfill this row.",
                    lead.id,
                )
        return await self._recalculate_score(lead)

    async def update(self, lead: Lead, data: LeadUpdate, user_id: int) -> Lead:
        """Update a lead and recalculate score.

        Refuses to flip ``status`` to ``'converted'`` directly. The only
        legitimate way to land in that state is through the Convert flow
        (`/leads/{id}/convert`), which actually creates the Contact +
        Opportunity and stamps `converted_contact_id`. Letting the edit
        form set it manually leaves an orphan-converted row that hides
        the Convert button while creating no downstream records.
        """
        update_data = data.model_dump(exclude_unset=True)
        if (
            update_data.get("status") == "converted"
            and lead.converted_contact_id is None
        ):
            raise LeadValidationError(
                "Use the Convert action — setting status to 'converted' "
                "directly skips creating the contact and opportunity.",
            )
        lead = await super().update(lead, data, user_id)
        return await self._recalculate_score(lead)

    async def _first_lead_stage_id(self) -> int | None:
        result = await self.db.execute(
            select(PipelineStage.id)
            .where(PipelineStage.pipeline_type == "lead")
            .where(PipelineStage.is_active.is_(True))
            .order_by(PipelineStage.order)
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _recalculate_score(self, lead: Lead) -> Lead:
        source_name: str | None = None
        if lead.source_id:
            source = await self.get_source_by_id(lead.source_id)
            source_name = source.name if source else None

        score, score_factors = calculate_lead_score(lead, source_name)
        lead.score = score
        lead.score_factors = score_factors

        await self.db.flush()
        await self.db.refresh(lead)
        return lead


    # Lead Source methods
    async def get_source_by_id(self, source_id: int) -> LeadSource | None:
        result = await self.db.execute(
            select(LeadSource).where(LeadSource.id == source_id)
        )
        return result.scalar_one_or_none()

    async def get_all_sources(self, active_only: bool = True) -> list[LeadSource]:
        query = select(LeadSource)
        if active_only:
            query = query.where(LeadSource.is_active == True)
        query = query.order_by(LeadSource.name)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def create_source(self, data: LeadSourceCreate) -> LeadSource:
        source = LeadSource(**data.model_dump())
        self.db.add(source)
        await self.db.flush()
        await self.db.refresh(source)
        return source

    async def update_source(
        self, source_id: int, data: LeadSourceUpdate
    ) -> LeadSource | None:
        source = await self.get_source_by_id(source_id)
        if source is None:
            return None
        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(source, key, value)
        await self.db.flush()
        await self.db.refresh(source)
        return source

    async def count_leads_by_source(self, source_id: int) -> int:
        result = await self.db.execute(
            select(func.count(Lead.id)).where(Lead.source_id == source_id)
        )
        return result.scalar_one()

    async def delete_source(self, source: LeadSource) -> None:
        # Caller is expected to have already loaded the source (e.g.
        # via get_source_by_id) so we don't double-fetch here. The
        # router's 404 path produces the not-found error before we
        # land in this method.
        await self.db.delete(source)
        await self.db.flush()
