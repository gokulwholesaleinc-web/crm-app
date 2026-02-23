"""Contract API routes."""

import logging
from typing import Optional
from fastapi import APIRouter, Query, Request
from src.core.constants import HTTPStatus, EntityNames
from src.core.router_utils import (
    DBSession,
    CurrentUser,
    get_entity_or_404,
    calculate_pages,
    check_ownership,
)
from src.contracts.schemas import (
    ContractCreate,
    ContractUpdate,
    ContractResponse,
    ContractListResponse,
)
from src.contracts.service import ContractService
from src.audit.utils import audit_entity_create, audit_entity_update, audit_entity_delete, snapshot_entity

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/contracts", tags=["contracts"])

ENTITY_NAME = "Contract"


@router.get("", response_model=ContractListResponse)
async def list_contracts(
    current_user: CurrentUser,
    db: DBSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    contact_id: Optional[int] = None,
    company_id: Optional[int] = None,
    status: Optional[str] = None,
    owner_id: Optional[int] = None,
):
    """List contracts with pagination and filters."""
    service = ContractService(db)

    contracts, total = await service.get_list(
        page=page,
        page_size=page_size,
        contact_id=contact_id,
        company_id=company_id,
        status=status,
        owner_id=owner_id,
    )

    contract_responses = [
        ContractResponse.model_validate(c) for c in contracts
    ]

    return ContractListResponse(
        items=contract_responses,
        total=total,
        page=page,
        page_size=page_size,
        pages=calculate_pages(total, page_size),
    )


@router.post("", response_model=ContractResponse, status_code=HTTPStatus.CREATED)
async def create_contract(
    contract_data: ContractCreate,
    request: Request,
    current_user: CurrentUser,
    db: DBSession,
):
    """Create a new contract."""
    service = ContractService(db)
    contract = await service.create(contract_data, current_user.id)

    ip_address = request.client.host if request.client else None
    await audit_entity_create(db, "contract", contract.id, current_user.id, ip_address)

    return ContractResponse.model_validate(contract)


@router.get("/{contract_id}", response_model=ContractResponse)
async def get_contract(
    contract_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Get a contract by ID."""
    service = ContractService(db)
    contract = await get_entity_or_404(service, contract_id, ENTITY_NAME)
    return ContractResponse.model_validate(contract)


@router.patch("/{contract_id}", response_model=ContractResponse)
async def update_contract(
    contract_id: int,
    contract_data: ContractUpdate,
    request: Request,
    current_user: CurrentUser,
    db: DBSession,
):
    """Update a contract."""
    service = ContractService(db)
    contract = await get_entity_or_404(service, contract_id, ENTITY_NAME)
    check_ownership(contract, current_user, ENTITY_NAME)

    update_fields = list(contract_data.model_dump(exclude_unset=True).keys())
    old_data = snapshot_entity(contract, update_fields)

    updated_contract = await service.update(contract, contract_data, current_user.id)

    new_data = snapshot_entity(updated_contract, update_fields)
    ip_address = request.client.host if request.client else None
    await audit_entity_update(db, "contract", updated_contract.id, current_user.id, old_data, new_data, ip_address)

    return ContractResponse.model_validate(updated_contract)


@router.delete("/{contract_id}", status_code=HTTPStatus.NO_CONTENT)
async def delete_contract(
    contract_id: int,
    request: Request,
    current_user: CurrentUser,
    db: DBSession,
):
    """Delete a contract."""
    service = ContractService(db)
    contract = await get_entity_or_404(service, contract_id, ENTITY_NAME)
    check_ownership(contract, current_user, ENTITY_NAME)

    ip_address = request.client.host if request.client else None
    await audit_entity_delete(db, "contract", contract.id, current_user.id, ip_address)

    await service.delete(contract)
