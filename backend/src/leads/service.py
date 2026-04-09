"""Lead service layer."""

from typing import Optional, List, Tuple, Any, Dict
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from src.leads.models import Lead, LeadSource
from src.core.filtering import apply_filters_to_query, build_token_search
from src.leads.schemas import LeadCreate, LeadUpdate, LeadSourceCreate
from src.leads.scoring import calculate_lead_score
from src.core.base_service import CRUDService, TaggableServiceMixin
from src.core.constants import ENTITY_TYPE_LEADS, DEFAULT_PAGE_SIZE


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
        search: Optional[str] = None,
        status: Optional[str] = None,
        source_id: Optional[int] = None,
        owner_id: Optional[int] = None,
        min_score: Optional[int] = None,
        tag_ids: Optional[List[int]] = None,
        filters: Optional[Dict[str, Any]] = None,
        shared_entity_ids: Optional[List[int]] = None,
    ) -> Tuple[List[Lead], int]:
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

        return await self.paginate_query(query, page, page_size, order_by=Lead.score.desc())

    async def create(self, data: LeadCreate, user_id: int) -> Lead:
        """Create a new lead with auto-scoring."""
        lead = await super().create(data, user_id)

        # Calculate and set lead score
        source_name = None
        if lead.source_id:
            source = await self.get_source_by_id(lead.source_id)
            source_name = source.name if source else None

        score, score_factors = calculate_lead_score(lead, source_name)
        lead.score = score
        lead.score_factors = score_factors

        await self.db.flush()
        await self.db.refresh(lead)
        return lead

    async def update(self, lead: Lead, data: LeadUpdate, user_id: int) -> Lead:
        """Update a lead and recalculate score."""
        lead = await super().update(lead, data, user_id)

        # Recalculate score
        source_name = None
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
    async def get_source_by_id(self, source_id: int) -> Optional[LeadSource]:
        """Get lead source by ID."""
        result = await self.db.execute(
            select(LeadSource).where(LeadSource.id == source_id)
        )
        return result.scalar_one_or_none()

    async def get_all_sources(self, active_only: bool = True) -> List[LeadSource]:
        """Get all lead sources."""
        query = select(LeadSource)
        if active_only:
            query = query.where(LeadSource.is_active == True)
        query = query.order_by(LeadSource.name)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def create_source(self, data: LeadSourceCreate) -> LeadSource:
        """Create a new lead source."""
        source = LeadSource(**data.model_dump())
        self.db.add(source)
        await self.db.flush()
        await self.db.refresh(source)
        return source
