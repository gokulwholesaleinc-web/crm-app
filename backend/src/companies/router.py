"""Company API routes."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select

from src.ai.embedding_hooks import (
    build_company_embedding_content,
    delete_entity_embedding,
    store_entity_embedding,
)
from src.audit.utils import (
    audit_entity_create,
    audit_entity_delete,
    audit_entity_update,
    snapshot_entity,
)
from src.companies.schemas import (
    CompanyCreate,
    CompanyListResponse,
    CompanyResponse,
    CompanyUpdate,
    TagBrief,
)
from src.companies.service import CompanyService
from src.contacts.models import Contact
from src.core.constants import ENTITY_TYPE_COMPANIES, EntityNames, HTTPStatus
from src.core.data_scope import DataScope, check_record_access_or_shared, get_data_scope
from src.core.router_utils import (
    CurrentUser,
    DBSession,
    calculate_pages,
    check_ownership,
    effective_owner_id,
    get_entity_or_404,
    parse_json_filters,
    parse_tag_ids,
)
from src.events.service import COMPANY_CREATED, COMPANY_UPDATED, emit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/companies", tags=["companies"])


async def _build_company_response(
    service: CompanyService, company, include_contact_count: bool = True
) -> CompanyResponse:
    """Build a CompanyResponse with tags and optional contact count."""
    tags = await service.get_tags(company.id)
    response_dict = CompanyResponse.model_validate(company).model_dump()
    response_dict["tags"] = [TagBrief.model_validate(t) for t in tags]
    if include_contact_count:
        response_dict["contact_count"] = await service.get_contact_count(company.id)
    return CompanyResponse(**response_dict)


@router.get("", response_model=CompanyListResponse)
async def list_companies(
    current_user: CurrentUser,
    db: DBSession,
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = None,
    status: str | None = None,
    industry: str | None = None,
    owner_id: int | None = None,
    tag_ids: str | None = None,
    filters: str | None = None,
):
    """List companies with pagination and filters."""
    service = CompanyService(db)

    companies, total = await service.get_list(
        page=page,
        page_size=page_size,
        search=search,
        status=status,
        industry=industry,
        owner_id=effective_owner_id(data_scope, owner_id),
        tag_ids=parse_tag_ids(tag_ids),
        filters=parse_json_filters(filters),
        shared_entity_ids=data_scope.get_shared_ids(ENTITY_TYPE_COMPANIES),
    )

    # Bulk-load tags and contact counts to avoid N+1 queries
    company_ids = [c.id for c in companies]
    tags_map = await service.get_tags_for_entities(company_ids)
    counts_map = await service.get_contact_counts_batch(company_ids)

    company_responses = []
    for company in companies:
        response_dict = CompanyResponse.model_validate(company).model_dump()
        response_dict["tags"] = [TagBrief.model_validate(t) for t in tags_map.get(company.id, [])]
        response_dict["contact_count"] = counts_map.get(company.id, 0)
        company_responses.append(CompanyResponse(**response_dict))

    return CompanyListResponse(
        items=company_responses,
        total=total,
        page=page,
        page_size=page_size,
        pages=calculate_pages(total, page_size),
    )


@router.post("", response_model=CompanyResponse, status_code=HTTPStatus.CREATED)
async def create_company(
    company_data: CompanyCreate,
    request: Request,
    current_user: CurrentUser,
    db: DBSession,
):
    """Create a new company."""
    service = CompanyService(db)
    company = await service.create(company_data, current_user.id)

    # Generate embedding for semantic search
    try:
        content = build_company_embedding_content(company)
        await store_entity_embedding(db, "company", company.id, content)
    except Exception as e:
        logger.warning("Failed to store embedding: %s", e)

    ip_address = request.client.host if request.client else None
    await audit_entity_create(db, "company", company.id, current_user.id, ip_address)

    await emit(COMPANY_CREATED, {
        "entity_id": company.id,
        "entity_type": "company",
        "user_id": current_user.id,
        "data": {"name": company.name, "industry": company.industry, "status": company.status},
    })

    # New company has no contacts, so pass include_contact_count=False to avoid query
    # and manually set contact_count to 0
    response = await _build_company_response(service, company, include_contact_count=False)
    response_dict = response.model_dump()
    response_dict["contact_count"] = 0
    return CompanyResponse(**response_dict)


@router.get("/{company_id}", response_model=CompanyResponse)
async def get_company(
    company_id: int,
    current_user: CurrentUser,
    db: DBSession,
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
):
    """Get a company by ID."""
    service = CompanyService(db)
    company = await get_entity_or_404(service, company_id, EntityNames.COMPANY)
    check_record_access_or_shared(
        company, current_user, data_scope.role_name,
        shared_entity_ids=data_scope.get_shared_ids(ENTITY_TYPE_COMPANIES),
    )
    return await _build_company_response(service, company)


@router.patch("/{company_id}", response_model=CompanyResponse)
async def update_company(
    company_id: int,
    company_data: CompanyUpdate,
    request: Request,
    current_user: CurrentUser,
    db: DBSession,
):
    """Update a company."""
    service = CompanyService(db)
    company = await get_entity_or_404(service, company_id, EntityNames.COMPANY)
    check_ownership(company, current_user, EntityNames.COMPANY)

    update_fields = list(company_data.model_dump(exclude_unset=True).keys())
    old_data = snapshot_entity(company, update_fields)

    updated_company = await service.update(company, company_data, current_user.id)

    # Update embedding for semantic search
    try:
        content = build_company_embedding_content(updated_company)
        await store_entity_embedding(db, "company", updated_company.id, content)
    except Exception as e:
        logger.warning("Failed to store embedding: %s", e)

    new_data = snapshot_entity(updated_company, update_fields)
    ip_address = request.client.host if request.client else None
    await audit_entity_update(db, "company", updated_company.id, current_user.id, old_data, new_data, ip_address)

    await emit(COMPANY_UPDATED, {
        "entity_id": updated_company.id,
        "entity_type": "company",
        "user_id": current_user.id,
        "data": {"name": updated_company.name, "industry": updated_company.industry, "status": updated_company.status},
    })

    return await _build_company_response(service, updated_company)


@router.delete("/{company_id}", status_code=HTTPStatus.NO_CONTENT)
async def delete_company(
    company_id: int,
    request: Request,
    current_user: CurrentUser,
    db: DBSession,
):
    """Delete a company."""
    service = CompanyService(db)
    company = await get_entity_or_404(service, company_id, EntityNames.COMPANY)
    check_ownership(company, current_user, EntityNames.COMPANY)

    # Block delete when contacts still reference this company — otherwise
    # the FK set-null cascade would silently orphan them.
    count_result = await db.execute(
        select(func.count()).select_from(Contact).where(Contact.company_id == company_id)
    )
    contact_count = count_result.scalar() or 0
    if contact_count > 0:
        raise HTTPException(
            status_code=HTTPStatus.CONFLICT,
            detail=f"Cannot delete company with {contact_count} contacts. Reassign or delete the contacts first.",
        )

    ip_address = request.client.host if request.client else None
    await audit_entity_delete(db, "company", company.id, current_user.id, ip_address)

    # Delete embedding before deleting entity
    await delete_entity_embedding(db, "company", company.id)

    await service.delete(company)
