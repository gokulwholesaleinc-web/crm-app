"""Company service layer."""

from typing import Optional, List, Tuple
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from src.companies.models import Company
from src.companies.schemas import CompanyCreate, CompanyUpdate
from src.core.models import Tag, EntityTag
from src.contacts.models import Contact


class CompanyService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, company_id: int) -> Optional[Company]:
        """Get company by ID."""
        result = await self.db.execute(
            select(Company).where(Company.id == company_id)
        )
        return result.scalar_one_or_none()

    async def get_list(
        self,
        page: int = 1,
        page_size: int = 20,
        search: Optional[str] = None,
        status: Optional[str] = None,
        industry: Optional[str] = None,
        owner_id: Optional[int] = None,
        tag_ids: Optional[List[int]] = None,
    ) -> Tuple[List[Company], int]:
        """Get paginated list of companies with filters."""
        query = select(Company)

        # Apply filters
        if search:
            search_filter = or_(
                Company.name.ilike(f"%{search}%"),
                Company.email.ilike(f"%{search}%"),
                Company.website.ilike(f"%{search}%"),
            )
            query = query.where(search_filter)

        if status:
            query = query.where(Company.status == status)

        if industry:
            query = query.where(Company.industry == industry)

        if owner_id:
            query = query.where(Company.owner_id == owner_id)

        if tag_ids:
            tag_subquery = (
                select(EntityTag.entity_id)
                .where(EntityTag.entity_type == "companies")
                .where(EntityTag.tag_id.in_(tag_ids))
                .group_by(EntityTag.entity_id)
                .having(func.count(EntityTag.tag_id) == len(tag_ids))
            )
            query = query.where(Company.id.in_(tag_subquery))

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar()

        # Apply pagination
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(Company.created_at.desc())

        result = await self.db.execute(query)
        companies = list(result.scalars().all())

        return companies, total

    async def create(self, data: CompanyCreate, user_id: int) -> Company:
        """Create a new company."""
        company_data = data.model_dump(exclude={"tag_ids"})
        company = Company(**company_data, created_by_id=user_id)
        self.db.add(company)
        await self.db.flush()

        if data.tag_ids:
            await self._update_tags(company.id, data.tag_ids)

        await self.db.refresh(company)
        return company

    async def update(self, company: Company, data: CompanyUpdate, user_id: int) -> Company:
        """Update a company."""
        update_data = data.model_dump(exclude={"tag_ids"}, exclude_unset=True)
        for field, value in update_data.items():
            setattr(company, field, value)
        company.updated_by_id = user_id
        await self.db.flush()

        if data.tag_ids is not None:
            await self._update_tags(company.id, data.tag_ids)

        await self.db.refresh(company)
        return company

    async def delete(self, company: Company) -> None:
        """Delete a company."""
        await self.db.execute(
            EntityTag.__table__.delete().where(
                EntityTag.entity_type == "companies",
                EntityTag.entity_id == company.id,
            )
        )
        await self.db.delete(company)
        await self.db.flush()

    async def _update_tags(self, company_id: int, tag_ids: List[int]) -> None:
        """Update tags for a company."""
        await self.db.execute(
            EntityTag.__table__.delete().where(
                EntityTag.entity_type == "companies",
                EntityTag.entity_id == company_id,
            )
        )

        for tag_id in tag_ids:
            entity_tag = EntityTag(
                entity_type="companies",
                entity_id=company_id,
                tag_id=tag_id,
            )
            self.db.add(entity_tag)
        await self.db.flush()

    async def get_company_tags(self, company_id: int) -> List[Tag]:
        """Get tags for a company."""
        result = await self.db.execute(
            select(Tag)
            .join(EntityTag)
            .where(EntityTag.entity_type == "companies")
            .where(EntityTag.entity_id == company_id)
        )
        return list(result.scalars().all())

    async def get_contact_count(self, company_id: int) -> int:
        """Get count of contacts for a company."""
        result = await self.db.execute(
            select(func.count()).where(Contact.company_id == company_id)
        )
        return result.scalar() or 0
