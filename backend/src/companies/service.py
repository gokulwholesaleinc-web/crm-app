"""Company service layer."""

from typing import Optional, List, Tuple, Any, Dict
from sqlalchemy import select, func, or_
from src.companies.models import Company
from src.core.filtering import apply_filters_to_query
from src.companies.schemas import CompanyCreate, CompanyUpdate
from src.contacts.models import Contact
from src.core.base_service import CRUDService, TaggableServiceMixin
from src.core.constants import ENTITY_TYPE_COMPANIES, DEFAULT_PAGE_SIZE


class CompanyService(
    CRUDService[Company, CompanyCreate, CompanyUpdate],
    TaggableServiceMixin,
):
    """Service for Company CRUD operations with tag support."""

    model = Company
    entity_type = ENTITY_TYPE_COMPANIES

    async def get_list(
        self,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
        search: Optional[str] = None,
        status: Optional[str] = None,
        industry: Optional[str] = None,
        owner_id: Optional[int] = None,
        tag_ids: Optional[List[int]] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> Tuple[List[Company], int]:
        """Get paginated list of companies with filters."""
        query = select(Company)

        if filters:
            query = apply_filters_to_query(query, Company, filters)

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
            query = await self._filter_by_tags(query, tag_ids)

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
        company = await super().create(data, user_id)

        if data.tag_ids:
            await self.update_tags(company.id, data.tag_ids)
            await self.db.refresh(company)

        return company

    async def update(self, company: Company, data: CompanyUpdate, user_id: int) -> Company:
        """Update a company."""
        company = await super().update(company, data, user_id)

        if data.tag_ids is not None:
            await self.update_tags(company.id, data.tag_ids)
            await self.db.refresh(company)

        return company

    async def delete(self, company: Company) -> None:
        """Delete a company."""
        await self.clear_tags(company.id)
        await super().delete(company)


    async def get_contact_count(self, company_id: int) -> int:
        """Get count of contacts for a company."""
        result = await self.db.execute(
            select(func.count()).where(Contact.company_id == company_id)
        )
        return result.scalar() or 0
