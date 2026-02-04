"""Lead service layer."""

from typing import Optional, List, Tuple
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from src.leads.models import Lead, LeadSource
from src.leads.schemas import LeadCreate, LeadUpdate, LeadSourceCreate
from src.leads.scoring import calculate_lead_score
from src.core.models import Tag, EntityTag


class LeadService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, lead_id: int) -> Optional[Lead]:
        """Get lead by ID with related data."""
        result = await self.db.execute(
            select(Lead)
            .where(Lead.id == lead_id)
            .options(selectinload(Lead.source))
        )
        return result.scalar_one_or_none()

    async def get_list(
        self,
        page: int = 1,
        page_size: int = 20,
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
            tag_subquery = (
                select(EntityTag.entity_id)
                .where(EntityTag.entity_type == "leads")
                .where(EntityTag.tag_id.in_(tag_ids))
                .group_by(EntityTag.entity_id)
                .having(func.count(EntityTag.tag_id) == len(tag_ids))
            )
            query = query.where(Lead.id.in_(tag_subquery))

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
        lead_data = data.model_dump(exclude={"tag_ids"})
        lead = Lead(**lead_data, created_by_id=user_id)
        self.db.add(lead)
        await self.db.flush()

        # Calculate and set lead score
        source_name = None
        if lead.source_id:
            source = await self.get_source_by_id(lead.source_id)
            source_name = source.name if source else None

        score, score_factors = calculate_lead_score(lead, source_name)
        lead.score = score
        lead.score_factors = score_factors

        if data.tag_ids:
            await self._update_tags(lead.id, data.tag_ids)

        await self.db.flush()
        await self.db.refresh(lead)
        return lead

    async def update(self, lead: Lead, data: LeadUpdate, user_id: int) -> Lead:
        """Update a lead and recalculate score."""
        update_data = data.model_dump(exclude={"tag_ids"}, exclude_unset=True)
        for field, value in update_data.items():
            setattr(lead, field, value)
        lead.updated_by_id = user_id

        # Recalculate score
        source_name = None
        if lead.source_id:
            source = await self.get_source_by_id(lead.source_id)
            source_name = source.name if source else None

        score, score_factors = calculate_lead_score(lead, source_name)
        lead.score = score
        lead.score_factors = score_factors

        if data.tag_ids is not None:
            await self._update_tags(lead.id, data.tag_ids)

        await self.db.flush()
        await self.db.refresh(lead)
        return lead

    async def delete(self, lead: Lead) -> None:
        """Delete a lead."""
        await self.db.execute(
            EntityTag.__table__.delete().where(
                EntityTag.entity_type == "leads",
                EntityTag.entity_id == lead.id,
            )
        )
        await self.db.delete(lead)
        await self.db.flush()

    async def _update_tags(self, lead_id: int, tag_ids: List[int]) -> None:
        """Update tags for a lead."""
        await self.db.execute(
            EntityTag.__table__.delete().where(
                EntityTag.entity_type == "leads",
                EntityTag.entity_id == lead_id,
            )
        )

        for tag_id in tag_ids:
            entity_tag = EntityTag(
                entity_type="leads",
                entity_id=lead_id,
                tag_id=tag_id,
            )
            self.db.add(entity_tag)
        await self.db.flush()

    async def get_lead_tags(self, lead_id: int) -> List[Tag]:
        """Get tags for a lead."""
        result = await self.db.execute(
            select(Tag)
            .join(EntityTag)
            .where(EntityTag.entity_type == "leads")
            .where(EntityTag.entity_id == lead_id)
        )
        return list(result.scalars().all())

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
