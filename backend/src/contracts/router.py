"""Contract API routes."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse

from src.audit.utils import (
    audit_entity_create,
    audit_entity_delete,
    audit_entity_update,
    snapshot_entity,
)
from src.config import settings
from src.contracts.schemas import (
    ContractCreate,
    ContractListResponse,
    ContractPublicView,
    ContractResponse,
    ContractSendRequest,
    ContractSendResponse,
    ContractSignRequest,
    ContractSignResponse,
    ContractUpdate,
)
from src.contracts.service import ContractService
from src.core.client_ip import get_client_ip
from src.core.constants import ENTITY_TYPE_CONTRACTS, HTTPStatus
from src.core.data_scope import DataScope, check_record_access_or_shared, get_data_scope
from src.core.rate_limit import limiter
from src.core.router_utils import (
    CurrentUser,
    DBSession,
    calculate_pages,
    check_ownership,
    get_entity_or_404,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/contracts", tags=["contracts"])

ENTITY_NAME = "Contract"


@router.get("", response_model=ContractListResponse)
async def list_contracts(
    current_user: CurrentUser,
    db: DBSession,
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    contact_id: int | None = None,
    company_id: int | None = None,
    status: str | None = None,
    owner_id: int | None = None,
    search: str | None = None,
    order_by: str | None = None,
    order_dir: str | None = None,
):
    """List contracts with pagination, filters, search, and sort."""
    effective_owner_id = owner_id if data_scope.can_see_all() else data_scope.owner_id

    service = ContractService(db)

    contracts, total = await service.get_list(
        page=page,
        page_size=page_size,
        contact_id=contact_id,
        company_id=company_id,
        status=status,
        owner_id=effective_owner_id,
        shared_entity_ids=data_scope.get_shared_ids(ENTITY_TYPE_CONTRACTS),
        search=search,
        order_by=order_by,
        order_dir=order_dir,
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

    ip_address = get_client_ip(request)
    await audit_entity_create(db, "contract", contract.id, current_user.id, ip_address)

    return ContractResponse.model_validate(contract)


@router.get("/{contract_id}", response_model=ContractResponse)
async def get_contract(
    contract_id: int,
    current_user: CurrentUser,
    db: DBSession,
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
):
    """Get a contract by ID."""
    service = ContractService(db)
    contract = await get_entity_or_404(service, contract_id, ENTITY_NAME)
    check_record_access_or_shared(
        contract, current_user, data_scope.role_name,
        shared_entity_ids=data_scope.get_shared_ids(ENTITY_TYPE_CONTRACTS),
    )
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
    ip_address = get_client_ip(request)
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

    ip_address = get_client_ip(request)
    await audit_entity_delete(db, "contract", contract.id, current_user.id, ip_address)

    await service.delete(contract)


# ---------- Signed PDF download ----------


@router.get("/{contract_id}/signed-pdf")
async def download_signed_pdf(
    contract_id: int,
    current_user: CurrentUser,
    db: DBSession,
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
):
    """Redirect to a short-lived presigned URL for the signed PDF stored in R2."""
    from src.attachments.object_storage import get_download_url

    service = ContractService(db)
    contract = await get_entity_or_404(service, contract_id, ENTITY_NAME)
    check_record_access_or_shared(
        contract, current_user, data_scope.role_name,
        shared_entity_ids=data_scope.get_shared_ids(ENTITY_TYPE_CONTRACTS),
    )

    if not contract.signed_pdf_r2_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Signed PDF not available for this contract",
        )

    try:
        url = await get_download_url(contract.signed_pdf_r2_key, ttl_sec=300)
    except Exception as exc:
        logger.exception(
            "Failed to generate presigned URL for contract %s",
            contract_id,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="File storage unavailable — try again later",
        ) from exc

    return RedirectResponse(url=url, status_code=307)


# ---------- E-sign workflow ----------


@router.post(
    "/{contract_id}/send",
    response_model=ContractSendResponse,
    status_code=HTTPStatus.OK,
)
async def send_contract_for_signature(
    contract_id: int,
    body: ContractSendRequest,
    request: Request,
    current_user: CurrentUser,
    db: DBSession,
):
    """Mint a sign token and email the contact a public link to sign."""
    service = ContractService(db)
    contract = await get_entity_or_404(service, contract_id, ENTITY_NAME)
    check_ownership(contract, current_user, ENTITY_NAME)

    # Snapshot the inbound status so the audit row reflects the actual
    # transition (draft→sent on first send, sent→sent on re-send).
    old_status = contract.status

    try:
        contract = await service.send_for_signature(
            contract,
            user_id=current_user.id,
            to_email=body.to_email,
            message=body.message,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    # Audit row so the contract's lifecycle is correlatable across users.
    ip_address = get_client_ip(request)
    await audit_entity_update(
        db, "contract", contract.id, current_user.id,
        {"status": old_status}, {"status": "sent"}, ip_address,
    )

    base_url = settings.FRONTEND_BASE_URL or "http://localhost:3000"
    return ContractSendResponse(
        id=contract.id,
        status=contract.status,
        sent_at=contract.sent_at,
        sign_url=f"{base_url}/contracts/sign/{contract.sign_token}",
        sign_token_expires_at=contract.sign_token_expires_at,
    )


@router.get("/public/{token}", response_model=ContractPublicView)
@limiter.limit("60/minute")
async def get_public_contract(token: str, request: Request, db: DBSession):
    """Public, no-auth view of a contract by sign token."""
    service = ContractService(db)
    contract = await service.get_by_token(token)
    if contract is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sign link not found or expired",
        )

    view = await service.get_public_view(contract)
    return ContractPublicView(**view)


@router.post(
    "/public/{token}/sign",
    response_model=ContractSignResponse,
    status_code=HTTPStatus.OK,
)
@limiter.limit("10/minute")
async def sign_contract_public(
    token: str,
    body: ContractSignRequest,
    request: Request,
    db: DBSession,
):
    """Public sign endpoint — captures name, signature, IP, UA."""
    service = ContractService(db)
    contract = await service.get_by_token(token)
    if contract is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sign link not found or expired",
        )

    signer_ip = get_client_ip(request)
    signer_user_agent = request.headers.get("user-agent")

    try:
        contract = await service.sign_contract(
            contract,
            signer_name=body.signer_name,
            signer_email=body.signer_email,
            signature_data_url=body.signature_data_url,
            signer_ip=signer_ip,
            signer_user_agent=signer_user_agent,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    # contract_signed notification + email is dispatched by ContractService.sign_contract
    # via notify_on_contract_signed (matrix-gated). Don't double-fire from the router.

    # Audit row for the sign event. user_id=None marks a public-token
    # action — the audit log shouldn't misattribute it to a CRM user.
    # Wrapped in try/except so a transient audit failure can't 500 the
    # signer after they've already submitted (re-submit would 400 with
    # "Cannot sign contract in 'signed' status" — confusing UX).
    try:
        await audit_entity_update(
            db, "contract", contract.id, None,
            {"status": "sent"},
            {"status": "signed", "signed_by_name": body.signer_name},
            signer_ip,
        )
    except Exception:
        logger.exception(
            "Audit write failed after public sign for contract %s "
            "(contract was signed; audit row missing)",
            contract.id,
        )

    return ContractSignResponse(
        id=contract.id,
        status=contract.status,
        signed_at=contract.signed_at,
        signed_by_name=contract.signed_by_name,
    )
