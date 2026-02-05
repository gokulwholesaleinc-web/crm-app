"""Lead service layer."""

from typing import Optional, List, Tuple
from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload
from src.leads.models import Lead, LeadSource
from src.leads.schemas import LeadCreate, LeadUpdate, LeadSourceCreate
from src.leads.scoring import calculate_lead_score
from src.core.base_service import CRUDService, TaggableServiceMixin
from src.core.models import Tag
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
    ) -> Tuple[List[Lead], int]:
        """Get paginated list of leads with filters."""
        query = select(Lead).options(selectinload(Lead.source))

        if search:
            search_filter = or_(
                Lead.first_name.ilike(f"%{search}%"),
                Lead.last_name.ilike(f"%{search}%"),
                Lead.email.ilike(f"%{search}%"),
                Lead.company_name.ilike(f"%{search}%"),
            )
            query = query.where(search_filter)

        if status:
            query = query.where(Lead.status == status)

        if source_id:
            query = query.where(Lead.source_id == source_id)

        if owner_id:
            query = query.where(Lead.owner_id == owner_id)

        if min_score is not None:
            query = query.where(Lead.score >= min_score)

        if tag_ids:
            query = await self._filter_by_tags(query, tag_ids)

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar()

        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(Lead.score.desc(), Lead.created_at.desc())

        result = await self.db.execute(query)
        leads = list(result.scalars().all())

        return leads, total

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

        if data.tag_ids:
            await self.update_tags(lead.id, data.tag_ids)

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

        if data.tag_ids is not None:
            await self.update_tags(lead.id, data.tag_ids)

        await self.db.flush()
        await self.db.refresh(lead)
        return lead

    async def delete(self, lead: Lead) -> None:
        """Delete a lead."""
        await self.clear_tags(lead.id)
        await super().delete(lead)

    async def get_lead_tags(self, lead_id: int) -> List[Tag]:
        """Get tags for a lead."""
        return await self.get_tags(lead_id)

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
