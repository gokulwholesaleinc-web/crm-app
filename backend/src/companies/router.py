"""Company API routes."""

from typing import Annotated, Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_db
from src.auth.models import User
from src.auth.dependencies import get_current_active_user
from src.companies.models import Company
from src.companies.schemas import (
    CompanyCreate,
    CompanyUpdate,
    CompanyResponse,
    CompanyListResponse,
    TagBrief,
)
from src.companies.service import CompanyService

router = APIRouter(prefix="/api/companies", tags=["companies"])


@router.get("", response_model=CompanyListResponse)
async def list_companies(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    status: Optional[str] = None,
    industry: Optional[str] = None,
    owner_id: Optional[int] = None,
    tag_ids: Optional[str] = None,
):
    """List companies with pagination and filters."""
    service = CompanyService(db)

    parsed_tag_ids = None
    if tag_ids:
        parsed_tag_ids = [int(x) for x in tag_ids.split(",")]

    companies, total = await service.get_list(
        page=page,
        page_size=page_size,
        search=search,
        status=status,
        industry=industry,
        owner_id=owner_id,
        tag_ids=parsed_tag_ids,
    )

    company_responses = []
    for company in companies:
        tags = await service.get_company_tags(company.id)
        contact_count = await service.get_contact_count(company.id)
        company_dict = CompanyResponse.model_validate(company).model_dump()
        company_dict["tags"] = [TagBrief.model_validate(t) for t in tags]
        company_dict["contact_count"] = contact_count
        company_responses.append(CompanyResponse(**company_dict))

    pages = (total + page_size - 1) // page_size

    return CompanyListResponse(
        items=company_responses,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


@router.post("", response_model=CompanyResponse, status_code=status.HTTP_201_CREATED)
async def create_company(
    company_data: CompanyCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Create a new company."""
    service = CompanyService(db)
    company = await service.create(company_data, current_user.id)

    tags = await service.get_company_tags(company.id)
    response = CompanyResponse.model_validate(company)
    response_dict = response.model_dump()
    response_dict["tags"] = [TagBrief.model_validate(t) for t in tags]
    response_dict["contact_count"] = 0

    return CompanyResponse(**response_dict)


@router.get("/{company_id}", response_model=CompanyResponse)
async def get_company(
    company_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Get a company by ID."""
    service = CompanyService(db)
    company = await service.get_by_id(company_id)

    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company not found",
        )

    tags = await service.get_company_tags(company.id)
    contact_count = await service.get_contact_count(company.id)
    response = CompanyResponse.model_validate(company)
    response_dict = response.model_dump()
    response_dict["tags"] = [TagBrief.model_validate(t) for t in tags]
    response_dict["contact_count"] = contact_count

    return CompanyResponse(**response_dict)


@router.patch("/{company_id}", response_model=CompanyResponse)
async def update_company(
    company_id: int,
    company_data: CompanyUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Update a company."""
    service = CompanyService(db)
    company = await service.get_by_id(company_id)

    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company not found",
        )

    updated_company = await service.update(company, company_data, current_user.id)

    tags = await service.get_company_tags(updated_company.id)
    contact_count = await service.get_contact_count(updated_company.id)
    response = CompanyResponse.model_validate(updated_company)
    response_dict = response.model_dump()
    response_dict["tags"] = [TagBrief.model_validate(t) for t in tags]
    response_dict["contact_count"] = contact_count

    return CompanyResponse(**response_dict)


@router.delete("/{company_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_company(
    company_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Delete a company."""
    service = CompanyService(db)
    company = await service.get_by_id(company_id)

    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company not found",
        )

    await service.delete(company)
