"""Company API routes."""

import logging
from typing import Optional
from fastapi import APIRouter, Query
from src.core.constants import HTTPStatus, EntityNames
from src.core.router_utils import (
    DBSession,
    CurrentUser,
    parse_tag_ids,
    get_entity_or_404,
    calculate_pages,
    check_ownership,
)
from src.companies.schemas import (
    CompanyCreate,
    CompanyUpdate,
    CompanyResponse,
    CompanyListResponse,
    TagBrief,
)
from src.companies.service import CompanyService
from src.ai.embedding_hooks import (
    store_entity_embedding,
    delete_entity_embedding,
    build_company_embedding_content,
)

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
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    status: Optional[str] = None,
    industry: Optional[str] = None,
    owner_id: Optional[int] = None,
    tag_ids: Optional[str] = None,
    filters: Optional[str] = None,
):
    """List companies with pagination and filters."""
    import json as _json
    parsed_filters = _json.loads(filters) if filters else None

    service = CompanyService(db)

    companies, total = await service.get_list(
        page=page,
        page_size=page_size,
        search=search,
        status=status,
        industry=industry,
        owner_id=owner_id,
        tag_ids=parse_tag_ids(tag_ids),
        filters=parsed_filters,
    )

    company_responses = [
        await _build_company_response(service, company) for company in companies
    ]

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
):
    """Get a company by ID."""
    service = CompanyService(db)
    company = await get_entity_or_404(service, company_id, EntityNames.COMPANY)
    return await _build_company_response(service, company)


@router.patch("/{company_id}", response_model=CompanyResponse)
async def update_company(
    company_id: int,
    company_data: CompanyUpdate,
    current_user: CurrentUser,
    db: DBSession,
):
    """Update a company."""
    service = CompanyService(db)
    company = await get_entity_or_404(service, company_id, EntityNames.COMPANY)
    check_ownership(company, current_user, EntityNames.COMPANY)
    updated_company = await service.update(company, company_data, current_user.id)

    # Update embedding for semantic search
    try:
        content = build_company_embedding_content(updated_company)
        await store_entity_embedding(db, "company", updated_company.id, content)
    except Exception as e:
        logger.warning("Failed to store embedding: %s", e)

    return await _build_company_response(service, updated_company)


@router.delete("/{company_id}", status_code=HTTPStatus.NO_CONTENT)
async def delete_company(
    company_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Delete a company."""
    service = CompanyService(db)
    company = await get_entity_or_404(service, company_id, EntityNames.COMPANY)
    check_ownership(company, current_user, EntityNames.COMPANY)

    # Delete embedding before deleting entity
    await delete_entity_embedding(db, "company", company.id)

    await service.delete(company)
