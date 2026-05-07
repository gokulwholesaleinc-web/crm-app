"""Contract service layer."""

import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from src.contracts.models import Contract
from src.contracts.schemas import ContractCreate, ContractUpdate
from src.core.base_service import CRUDService
from src.core.constants import DEFAULT_PAGE_SIZE
from src.core.filtering import build_token_search
from src.core.sorting import build_order_clauses

ENTITY_TYPE_CONTRACTS = "contracts"

# Mirrors proposals: signing links are valid for 7 days from send.
SIGN_TOKEN_TTL = timedelta(days=7)

CONTRACT_SORTABLE_FIELDS = {
    "title": Contract.title,
    "status": Contract.status,
    "value": Contract.value,
    "end_date": Contract.end_date,
    "created_at": Contract.created_at,
}


class ContractService(CRUDService[Contract, ContractCreate, ContractUpdate]):
    """Service for Contract CRUD operations."""

    model = Contract
    entity_type = ENTITY_TYPE_CONTRACTS
    create_exclude_fields: set = set()
    update_exclude_fields: set = set()

    def _get_eager_load_options(self):
        return [
            selectinload(Contract.contact),
            selectinload(Contract.company),
        ]

    async def get_list(
        self,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
        contact_id: int | None = None,
        company_id: int | None = None,
        status: str | None = None,
        owner_id: int | None = None,
        search: str | None = None,
        order_by: str | None = None,
        order_dir: str | None = None,
    ) -> tuple[list[Contract], int]:
        """Get paginated list of contracts with filters."""
        query = select(Contract).options(
            selectinload(Contract.contact),
            selectinload(Contract.company),
        )

        if contact_id:
            query = query.where(Contract.contact_id == contact_id)

        if company_id:
            query = query.where(Contract.company_id == company_id)

        if status:
            query = query.where(Contract.status == status)

        if owner_id:
            query = query.where(Contract.owner_id == owner_id)

        if search:
            condition = build_token_search(search, Contract.title)
            if condition is not None:
                query = query.where(condition)

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        order_clauses = build_order_clauses(
            CONTRACT_SORTABLE_FIELDS,
            order_by,
            order_dir,
            default=[Contract.created_at.desc(), Contract.id.desc()],
        )
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(*order_clauses)

        result = await self.db.execute(query)
        contracts = list(result.scalars().all())

        return contracts, total

    async def get_by_token(self, token: str) -> Contract | None:
        """Resolve a contract by its public sign token.

        Used by the public view + sign endpoints. Returns None when the
        token is missing, malformed, or no contract carries it.
        """
        if not token or len(token) < 16:
            return None
        result = await self.db.execute(
            select(Contract)
            .options(selectinload(Contract.contact), selectinload(Contract.company))
            .where(Contract.sign_token == token),
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _mint_token() -> str:
        """Mint an unguessable URL-safe token for the public sign link."""
        return secrets.token_urlsafe(32)

    @staticmethod
    def _token_expiry() -> datetime:
        return datetime.now(UTC) + SIGN_TOKEN_TTL

    # ---------- E-sign workflow stubs (filled in by the e-sign worker) ----------

    async def send_for_signature(
        self,
        contract: Contract,
        user_id: int,
        to_email: str | None = None,
        message: str | None = None,
    ) -> Contract:
        """Mint a sign token, mark sent_at, and email the signer."""
        raise NotImplementedError(
            "send_for_signature is owned by the e-sign worker (Phase 2a).",
        )

    async def get_public_view(self, contract: Contract) -> dict:
        """Return the signer-facing projection of a contract."""
        raise NotImplementedError(
            "get_public_view is owned by the e-sign worker (Phase 2a).",
        )

    async def sign_contract(
        self,
        contract: Contract,
        signer_name: str,
        signer_email: str,
        signature_data_url: str,
        signer_ip: str | None = None,
        signer_ua: str | None = None,
    ) -> Contract:
        """Persist signature, generate signed PDF, email signer a copy."""
        raise NotImplementedError(
            "sign_contract is owned by the e-sign worker (Phase 2a).",
        )
