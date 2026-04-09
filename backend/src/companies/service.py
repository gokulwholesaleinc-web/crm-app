"""Company service layer."""

from typing import Optional, List, Tuple, Any, Dict
from sqlalchemy import select, func
from src.companies.models import Company
from src.core.filtering import apply_filters_to_query, build_token_search
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
        shared_entity_ids: Optional[List[int]] = None,
    ) -> Tuple[List[Company], int]:
        """Get paginated list of companies with filters.

        Soft-deleted companies (``status="merged"``, written by
        :class:`DedupService.merge_companies`) are hidden unless the
        caller explicitly asks for ``status="merged"`` — otherwise
        tombstones from the dedup flow would reappear in list/kanban
        views after a merge.
        """
        query = select(Company)

        if filters:
            query = apply_filters_to_query(query, Company, filters)

        if search:
            search_condition = build_token_search(search, Company.name, Company.email, Company.website)
            if search_condition is not None:
                query = query.where(search_condition)

        if status:
            query = query.where(Company.status == status)
        else:
            query = query.where(Company.status != "merged")

        if industry:
            query = query.where(Company.industry == industry)

        query = self.apply_owner_filter(query, owner_id, shared_entity_ids)

        if tag_ids:
            query = await self._filter_by_tags(query, tag_ids)

        return await self.paginate_query(query, page, page_size)


    async def get_contact_count(self, company_id: int) -> int:
        """Get count of contacts for a company."""
        result = await self.db.execute(
            select(func.count()).where(Contact.company_id == company_id)
        )
        return result.scalar() or 0

    async def get_contact_counts_batch(self, company_ids: List[int]) -> Dict[int, int]:
        """Get contact counts for multiple companies in a single query."""
        if not company_ids:
            return {}
        result = await self.db.execute(
            select(Contact.company_id, func.count(Contact.id))
            .where(Contact.company_id.in_(company_ids))
            .group_by(Contact.company_id)
        )
        counts = {row[0]: row[1] for row in result.all()}
        return {cid: counts.get(cid, 0) for cid in company_ids}
