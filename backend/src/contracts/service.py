"""Contract service layer."""

from typing import Optional, List, Tuple
from sqlalchemy import select, func
from src.contracts.models import Contract
from src.contracts.schemas import ContractCreate, ContractUpdate
from src.core.base_service import CRUDService
from src.core.constants import DEFAULT_PAGE_SIZE


ENTITY_TYPE_CONTRACTS = "contracts"


class ContractService(CRUDService[Contract, ContractCreate, ContractUpdate]):
    """Service for Contract CRUD operations."""

    model = Contract
    entity_type = ENTITY_TYPE_CONTRACTS
    create_exclude_fields: set = set()
    update_exclude_fields: set = set()

    async def get_list(
        self,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
        contact_id: Optional[int] = None,
        company_id: Optional[int] = None,
        status: Optional[str] = None,
        owner_id: Optional[int] = None,
    ) -> Tuple[List[Contract], int]:
        """Get paginated list of contracts with filters."""
        query = select(Contract)

        if contact_id:
            query = query.where(Contract.contact_id == contact_id)

        if company_id:
            query = query.where(Contract.company_id == company_id)

        if status:
            query = query.where(Contract.status == status)

        if owner_id:
            query = query.where(Contract.owner_id == owner_id)

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar()

        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(Contract.created_at.desc())

        result = await self.db.execute(query)
        contracts = list(result.scalars().all())

        return contracts, total
