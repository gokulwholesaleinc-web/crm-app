"""Lead API routes."""

from typing import Annotated, Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_db
from src.auth.models import User
from src.auth.dependencies import get_current_active_user
from src.leads.models import Lead
from src.leads.schemas import (
    LeadCreate,
    LeadUpdate,
    LeadResponse,
    LeadListResponse,
    LeadSourceCreate,
    LeadSourceResponse,
    LeadConvertToContactRequest,
    LeadConvertToOpportunityRequest,
    LeadFullConversionRequest,
    ConversionResponse,
    TagBrief,
)
from src.leads.service import LeadService
from src.leads.conversion import LeadConverter

router = APIRouter(prefix="/api/leads", tags=["leads"])


@router.get("", response_model=LeadListResponse)
async def list_leads(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    status: Optional[str] = None,
    source_id: Optional[int] = None,
    owner_id: Optional[int] = None,
    min_score: Optional[int] = None,
    tag_ids: Optional[str] = None,
):
    """List leads with pagination and filters."""
    service = LeadService(db)

    parsed_tag_ids = None
    if tag_ids:
        parsed_tag_ids = [int(x) for x in tag_ids.split(",")]

    leads, total = await service.get_list(
        page=page,
        page_size=page_size,
        search=search,
        status=status,
        source_id=source_id,
        owner_id=owner_id,
        min_score=min_score,
        tag_ids=parsed_tag_ids,
    )

    lead_responses = []
    for lead in leads:
        tags = await service.get_lead_tags(lead.id)
        lead_dict = LeadResponse.model_validate(lead).model_dump()
        lead_dict["tags"] = [TagBrief.model_validate(t) for t in tags]
        lead_responses.append(LeadResponse(**lead_dict))

    pages = (total + page_size - 1) // page_size

    return LeadListResponse(
        items=lead_responses,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


@router.post("", response_model=LeadResponse, status_code=status.HTTP_201_CREATED)
async def create_lead(
    lead_data: LeadCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Create a new lead."""
    service = LeadService(db)
    lead = await service.create(lead_data, current_user.id)

    tags = await service.get_lead_tags(lead.id)
    response = LeadResponse.model_validate(lead)
    response_dict = response.model_dump()
    response_dict["tags"] = [TagBrief.model_validate(t) for t in tags]

    return LeadResponse(**response_dict)


@router.get("/{lead_id}", response_model=LeadResponse)
async def get_lead(
    lead_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Get a lead by ID."""
    service = LeadService(db)
    lead = await service.get_by_id(lead_id)

    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found",
        )

    tags = await service.get_lead_tags(lead.id)
    response = LeadResponse.model_validate(lead)
    response_dict = response.model_dump()
    response_dict["tags"] = [TagBrief.model_validate(t) for t in tags]

    return LeadResponse(**response_dict)


@router.patch("/{lead_id}", response_model=LeadResponse)
async def update_lead(
    lead_id: int,
    lead_data: LeadUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Update a lead."""
    service = LeadService(db)
    lead = await service.get_by_id(lead_id)

    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found",
        )

    updated_lead = await service.update(lead, lead_data, current_user.id)

    tags = await service.get_lead_tags(updated_lead.id)
    response = LeadResponse.model_validate(updated_lead)
    response_dict = response.model_dump()
    response_dict["tags"] = [TagBrief.model_validate(t) for t in tags]

    return LeadResponse(**response_dict)


@router.delete("/{lead_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_lead(
    lead_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Delete a lead."""
    service = LeadService(db)
    lead = await service.get_by_id(lead_id)

    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found",
        )

    await service.delete(lead)


# Conversion endpoints
@router.post("/{lead_id}/convert/contact", response_model=ConversionResponse)
async def convert_to_contact(
    lead_id: int,
    request: LeadConvertToContactRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Convert a lead to a contact."""
    service = LeadService(db)
    lead = await service.get_by_id(lead_id)

    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found",
        )

    if lead.converted_contact_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Lead already converted to contact",
        )

    converter = LeadConverter(db)
    contact, company = await converter.convert_to_contact(
        lead=lead,
        user_id=current_user.id,
        company_id=request.company_id,
        create_company=request.create_company,
    )

    return ConversionResponse(
        lead_id=lead.id,
        contact_id=contact.id,
        company_id=company.id if company else None,
        message="Lead successfully converted to contact",
    )


@router.post("/{lead_id}/convert/opportunity", response_model=ConversionResponse)
async def convert_to_opportunity(
    lead_id: int,
    request: LeadConvertToOpportunityRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Convert a lead to an opportunity."""
    service = LeadService(db)
    lead = await service.get_by_id(lead_id)

    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found",
        )

    if lead.converted_opportunity_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Lead already converted to opportunity",
        )

    converter = LeadConverter(db)
    opportunity = await converter.convert_to_opportunity(
        lead=lead,
        user_id=current_user.id,
        pipeline_stage_id=request.pipeline_stage_id,
        contact_id=request.contact_id,
        company_id=request.company_id,
    )

    return ConversionResponse(
        lead_id=lead.id,
        opportunity_id=opportunity.id,
        message="Lead successfully converted to opportunity",
    )


@router.post("/{lead_id}/convert/full", response_model=ConversionResponse)
async def full_conversion(
    lead_id: int,
    request: LeadFullConversionRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Full lead conversion: Lead → Contact + Company + Opportunity."""
    service = LeadService(db)
    lead = await service.get_by_id(lead_id)

    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found",
        )

    if lead.converted_contact_id or lead.converted_opportunity_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Lead already converted",
        )

    converter = LeadConverter(db)
    contact, company, opportunity = await converter.full_conversion(
        lead=lead,
        user_id=current_user.id,
        pipeline_stage_id=request.pipeline_stage_id,
        create_company=request.create_company,
    )

    return ConversionResponse(
        lead_id=lead.id,
        contact_id=contact.id,
        company_id=company.id if company else None,
        opportunity_id=opportunity.id,
        message="Lead successfully converted to contact and opportunity",
    )


# Lead Sources endpoints
@router.get("/sources/", response_model=List[LeadSourceResponse])
async def list_sources(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    active_only: bool = True,
):
    """List all lead sources."""
    service = LeadService(db)
    sources = await service.get_all_sources(active_only=active_only)
    return sources


@router.post("/sources/", response_model=LeadSourceResponse, status_code=status.HTTP_201_CREATED)
async def create_source(
    source_data: LeadSourceCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Create a new lead source."""
    service = LeadService(db)
    source = await service.create_source(source_data)
    return source
