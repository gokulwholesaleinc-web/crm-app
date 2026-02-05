"""Lead API routes."""

from typing import Optional, List
from fastapi import APIRouter, Query
from src.core.constants import HTTPStatus, EntityNames, ErrorMessages
from src.core.router_utils import (
    DBSession,
    CurrentUser,
    parse_tag_ids,
    get_entity_or_404,
    calculate_pages,
    raise_bad_request,
    check_ownership,
)
from src.core.cache import (
    cached_fetch,
    CACHE_LEAD_SOURCES,
    invalidate_lead_sources_cache,
)
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
from src.ai.embedding_hooks import (
    store_entity_embedding,
    delete_entity_embedding,
    build_lead_embedding_content,
)

router = APIRouter(prefix="/api/leads", tags=["leads"])


async def _build_lead_response(service: LeadService, lead) -> LeadResponse:
    """Build a LeadResponse with tags."""
    tags = await service.get_lead_tags(lead.id)
    response_dict = LeadResponse.model_validate(lead).model_dump()
    response_dict["tags"] = [TagBrief.model_validate(t) for t in tags]
    return LeadResponse(**response_dict)


@router.get("", response_model=LeadListResponse)
async def list_leads(
    current_user: CurrentUser,
    db: DBSession,
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

    leads, total = await service.get_list(
        page=page,
        page_size=page_size,
        search=search,
        status=status,
        source_id=source_id,
        owner_id=owner_id,
        min_score=min_score,
        tag_ids=parse_tag_ids(tag_ids),
    )

    lead_responses = [await _build_lead_response(service, lead) for lead in leads]

    return LeadListResponse(
        items=lead_responses,
        total=total,
        page=page,
        page_size=page_size,
        pages=calculate_pages(total, page_size),
    )


@router.post("", response_model=LeadResponse, status_code=HTTPStatus.CREATED)
async def create_lead(
    lead_data: LeadCreate,
    current_user: CurrentUser,
    db: DBSession,
):
    """Create a new lead."""
    service = LeadService(db)
    lead = await service.create(lead_data, current_user.id)

    # Generate embedding for semantic search
    content = build_lead_embedding_content(lead)
    await store_entity_embedding(db, "lead", lead.id, content)

    return await _build_lead_response(service, lead)


@router.get("/{lead_id}", response_model=LeadResponse)
async def get_lead(
    lead_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Get a lead by ID."""
    service = LeadService(db)
    lead = await get_entity_or_404(service, lead_id, EntityNames.LEAD)
    return await _build_lead_response(service, lead)


@router.patch("/{lead_id}", response_model=LeadResponse)
async def update_lead(
    lead_id: int,
    lead_data: LeadUpdate,
    current_user: CurrentUser,
    db: DBSession,
):
    """Update a lead."""
    service = LeadService(db)
    lead = await get_entity_or_404(service, lead_id, EntityNames.LEAD)
    check_ownership(lead, current_user, EntityNames.LEAD)
    updated_lead = await service.update(lead, lead_data, current_user.id)

    # Update embedding for semantic search
    content = build_lead_embedding_content(updated_lead)
    await store_entity_embedding(db, "lead", updated_lead.id, content)

    return await _build_lead_response(service, updated_lead)


@router.delete("/{lead_id}", status_code=HTTPStatus.NO_CONTENT)
async def delete_lead(
    lead_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Delete a lead."""
    service = LeadService(db)
    lead = await get_entity_or_404(service, lead_id, EntityNames.LEAD)
    check_ownership(lead, current_user, EntityNames.LEAD)

    # Delete embedding before deleting entity
    await delete_entity_embedding(db, "lead", lead.id)

    await service.delete(lead)


# Conversion endpoints
@router.post("/{lead_id}/convert/contact", response_model=ConversionResponse)
async def convert_to_contact(
    lead_id: int,
    request: LeadConvertToContactRequest,
    current_user: CurrentUser,
    db: DBSession,
):
    """Convert a lead to a contact."""
    service = LeadService(db)
    lead = await get_entity_or_404(service, lead_id, EntityNames.LEAD)

    if lead.converted_contact_id:
        raise_bad_request(ErrorMessages.already_converted_to(EntityNames.LEAD, "contact"))

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
    current_user: CurrentUser,
    db: DBSession,
):
    """Convert a lead to an opportunity."""
    service = LeadService(db)
    lead = await get_entity_or_404(service, lead_id, EntityNames.LEAD)

    if lead.converted_opportunity_id:
        raise_bad_request(
            ErrorMessages.already_converted_to(EntityNames.LEAD, "opportunity")
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
    current_user: CurrentUser,
    db: DBSession,
):
    """Full lead conversion: Lead -> Contact + Company + Opportunity."""
    service = LeadService(db)
    lead = await get_entity_or_404(service, lead_id, EntityNames.LEAD)

    if lead.converted_contact_id or lead.converted_opportunity_id:
        raise_bad_request(ErrorMessages.already_converted(EntityNames.LEAD))

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
    current_user: CurrentUser,
    db: DBSession,
    active_only: bool = True,
):
    """List all lead sources (cached for 5 minutes)."""
    service = LeadService(db)

    async def fetch_sources():
        sources = await service.get_all_sources(active_only=active_only)
        # Convert to dicts for caching (ORM objects can't be cached across sessions)
        return [LeadSourceResponse.model_validate(s).model_dump() for s in sources]

    cached_sources = await cached_fetch(
        CACHE_LEAD_SOURCES,
        f"sources:{active_only}",
        fetch_sources,
    )
    return cached_sources


@router.post(
    "/sources/", response_model=LeadSourceResponse, status_code=HTTPStatus.CREATED
)
async def create_source(
    source_data: LeadSourceCreate,
    current_user: CurrentUser,
    db: DBSession,
):
    """Create a new lead source."""
    service = LeadService(db)
    source = await service.create_source(source_data)
    # Invalidate cache since we added a new source
    invalidate_lead_sources_cache()
    return source
