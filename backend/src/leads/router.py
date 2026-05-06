"""Lead API routes."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy import select, update

from src.ai.embedding_hooks import (
    build_lead_embedding_content,
    delete_entity_embedding,
    store_entity_embedding,
)
from src.audit.utils import (
    audit_entity_create,
    audit_entity_delete,
    audit_entity_update,
    snapshot_entity,
)
from src.auth.dependencies import get_current_superuser
from src.auth.models import User
from src.core.cache import (
    CACHE_LEAD_SOURCES,
    cached_fetch,
    invalidate_lead_sources_cache,
)
from src.core.client_ip import get_client_ip
from src.core.constants import ENTITY_TYPE_LEADS, EntityNames, ErrorMessages, HTTPStatus
from src.core.data_scope import DataScope, check_record_access_or_shared, get_data_scope
from src.core.permissions import require_permission
from src.core.router_utils import (
    CurrentUser,
    DBSession,
    build_list_responses_with_tags,
    build_response_with_tags,
    calculate_pages,
    check_ownership,
    effective_owner_id,
    get_entity_or_404,
    parse_json_filters,
    parse_tag_ids,
    raise_bad_request,
)
from src.events.service import LEAD_CREATED, LEAD_UPDATED, emit
from src.leads.conversion import LeadConverter
from src.leads.models import Lead
from src.leads.schemas import (
    ConversionResponse,
    KanbanLead,
    KanbanLeadStage,
    LeadConvertToContactRequest,
    LeadConvertToOpportunityRequest,
    LeadCreate,
    LeadFullConversionRequest,
    LeadKanbanResponse,
    LeadListResponse,
    LeadResponse,
    LeadSourceCreate,
    LeadSourceResponse,
    LeadSourceUpdate,
    LeadUpdate,
    MoveLeadRequest,
    SendCampaignRequest,
    TagBrief,
)
from src.leads.service import LeadService, LeadValidationError
from src.notifications.service import notify_on_assignment
from src.opportunities.models import PipelineStage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/leads", tags=["leads"])


async def _build_lead_response(service: LeadService, lead) -> LeadResponse:
    return await build_response_with_tags(service, lead, LeadResponse, TagBrief)


@router.get("", response_model=LeadListResponse)
async def list_leads(
    current_user: CurrentUser,
    db: DBSession,
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = None,
    status: str | None = None,
    source_id: int | None = None,
    owner_id: int | None = None,
    min_score: int | None = None,
    tag_ids: str | None = None,
    filters: str | None = None,
):
    """List leads with pagination and filters.

    Data scoping:
    - Admin/Manager: see all leads (or filter by owner_id if provided)
    - Sales_rep/Viewer: see only own leads + shared leads
    """
    service = LeadService(db)

    leads, total = await service.get_list(
        page=page,
        page_size=page_size,
        search=search,
        status=status,
        source_id=source_id,
        owner_id=effective_owner_id(data_scope, owner_id),
        min_score=min_score,
        tag_ids=parse_tag_ids(tag_ids),
        filters=parse_json_filters(filters),
        shared_entity_ids=data_scope.get_shared_ids(ENTITY_TYPE_LEADS),
    )

    tags_map = await service.get_tags_for_entities([l.id for l in leads])

    return LeadListResponse(
        items=build_list_responses_with_tags(leads, tags_map, LeadResponse, TagBrief),
        total=total,
        page=page,
        page_size=page_size,
        pages=calculate_pages(total, page_size),
    )


@router.post("", response_model=LeadResponse, status_code=HTTPStatus.CREATED)
async def create_lead(
    lead_data: LeadCreate,
    request: Request,
    current_user: Annotated[User, Depends(require_permission("leads", "create"))],
    db: DBSession,
):
    """Create a new lead."""
    service = LeadService(db)
    try:
        lead = await service.create(lead_data, current_user.id)
    except LeadValidationError as exc:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST, detail=str(exc),
        ) from exc

    # Generate embedding for semantic search
    try:
        content = build_lead_embedding_content(lead)
        await store_entity_embedding(db, "lead", lead.id, content)
    except Exception as e:
        logger.warning("Failed to store embedding: %s", e)

    ip_address = get_client_ip(request)
    await audit_entity_create(db, "lead", lead.id, current_user.id, ip_address)

    await emit(LEAD_CREATED, {
        "entity_id": lead.id,
        "entity_type": "lead",
        "user_id": current_user.id,
        "data": {"first_name": lead.first_name, "last_name": lead.last_name, "email": lead.email, "status": lead.status},
    })

    if lead.owner_id and lead.owner_id != current_user.id:
        await notify_on_assignment(db, lead.owner_id, "leads", lead.id, lead.full_name)

    return await _build_lead_response(service, lead)


# Lead Pipeline / Kanban endpoints (before parameterized routes)

@router.get("/pipeline-stages")
async def get_lead_pipeline_stages(
    current_user: CurrentUser,
    db: DBSession,
):
    """Get pipeline stages for leads (pipeline_type='lead')."""
    from src.opportunities.schemas import PipelineStageResponse

    result = await db.execute(
        select(PipelineStage)
        .where(PipelineStage.pipeline_type == "lead")
        .where(PipelineStage.is_active == True)
        .order_by(PipelineStage.order)
    )
    stages = result.scalars().all()
    return [PipelineStageResponse.model_validate(s) for s in stages]


@router.post("/backfill-pipeline-stages")
async def backfill_lead_pipeline_stages(
    db: DBSession,
    _admin: Annotated[User, Depends(get_current_superuser)],
):
    """Admin-only: assign the first active lead-typed stage to every lead
    that currently has `pipeline_stage_id` NULL.

    Idempotent — re-running is safe. Used to recover from the pre-default
    era where new leads were created without a stage and never showed up
    on the kanban.
    """
    first_stage_result = await db.execute(
        select(PipelineStage)
        .where(PipelineStage.pipeline_type == "lead")
        .where(PipelineStage.is_active.is_(True))
        .order_by(PipelineStage.order)
        .limit(1)
    )
    first_stage = first_stage_result.scalar_one_or_none()
    if first_stage is None:
        raise HTTPException(
            status_code=412,
            detail=(
                "No active lead pipeline stages exist. Run the seed script "
                "or create a PipelineStage row with pipeline_type='lead' first."
            ),
        )

    result = await db.execute(
        update(Lead)
        .where(Lead.pipeline_stage_id.is_(None))
        .values(pipeline_stage_id=first_stage.id)
    )
    await db.commit()

    return {
        "stage_id": first_stage.id,
        "stage_name": first_stage.name,
        "updated": result.rowcount,
    }


@router.get("/kanban", response_model=LeadKanbanResponse)
async def get_lead_kanban(
    current_user: CurrentUser,
    db: DBSession,
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
    owner_id: int | None = None,
):
    """Get Kanban board view of lead pipeline.

    Sales reps can only see their own pipeline; admin/manager can pass
    owner_id to view another user's kanban. Spoofed owner_id from a
    sales_rep is ignored and collapsed back to the caller.
    """
    # effective_owner_id() honors the scope: admin/manager keep the
    # requested owner_id (None = "everyone"); sales_rep/viewer gets
    # their own id regardless. Default to the caller's own pipeline
    # ONLY for non-admins — admins viewing /pipeline expect to see
    # every team member's leads, otherwise the kanban looks empty
    # whenever leads belong to someone else (the "I'm admin and the
    # board is empty even though I have 48 leads under another rep"
    # scenario).
    if data_scope.can_see_all():
        resolved_owner_id = effective_owner_id(data_scope, owner_id)
    else:
        resolved_owner_id = effective_owner_id(data_scope, owner_id) or current_user.id

    # Get all active lead pipeline stages
    stages_result = await db.execute(
        select(PipelineStage)
        .where(PipelineStage.pipeline_type == "lead")
        .where(PipelineStage.is_active == True)
        .order_by(PipelineStage.order)
    )
    stages = stages_result.scalars().all()

    if not stages:
        return LeadKanbanResponse(
            stages=[],
            message="No lead pipeline stages configured. Run the seed script or contact admin.",
        )

    # Pull every visible lead in one query, then group by stage in Python.
    # Lets us build the owner-id → full_name map from a single follow-up
    # User query instead of N (one per stage) or doing the .map() inside
    # each loop iteration.
    leads_query = select(Lead).where(
        Lead.pipeline_stage_id.in_([s.id for s in stages])
    )
    if resolved_owner_id:
        leads_query = leads_query.where(Lead.owner_id == resolved_owner_id)
    leads_query = leads_query.order_by(Lead.score.desc())
    leads_result = await db.execute(leads_query)
    all_leads = list(leads_result.scalars().all())

    owner_ids = {lead.owner_id for lead in all_leads if lead.owner_id is not None}
    if owner_ids:
        owners_result = await db.execute(
            select(User.id, User.full_name).where(User.id.in_(owner_ids))
        )
        owner_name_by_id: dict[int, str] = {
            row.id: row.full_name for row in owners_result.all()
        }
    else:
        owner_name_by_id = {}

    leads_by_stage: dict[int, list[Lead]] = {s.id: [] for s in stages}
    for lead in all_leads:
        leads_by_stage[lead.pipeline_stage_id].append(lead)

    kanban_stages = []
    for stage in stages:
        leads = leads_by_stage[stage.id]
        kanban_leads = [
            KanbanLead(
                id=lead.id,
                first_name=lead.first_name,
                last_name=lead.last_name,
                full_name=lead.full_name,
                email=lead.email,
                company_name=lead.company_name,
                score=lead.score,
                owner_id=lead.owner_id,
                owner_name=owner_name_by_id.get(lead.owner_id) if lead.owner_id else None,
            )
            for lead in leads
        ]

        kanban_stages.append(
            KanbanLeadStage(
                stage_id=stage.id,
                stage_name=stage.name,
                color=stage.color,
                probability=stage.probability,
                is_won=stage.is_won,
                is_lost=stage.is_lost,
                leads=kanban_leads,
                count=len(kanban_leads),
            )
        )

    return LeadKanbanResponse(stages=kanban_stages)


@router.post("/send-campaign")
async def send_campaign(
    request_data: SendCampaignRequest,
    current_user: CurrentUser,
    db: DBSession,
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
):
    """Send personalized email campaign to selected leads.

    Only sends to leads the caller can access (owned or shared). Leads
    outside the caller's data scope are silently filtered out of the
    batch — we intentionally do NOT surface "forbidden" per lead to
    avoid leaking which IDs exist in other users' pipelines.
    """
    from src.email.service import EmailService, render_template

    email_service = EmailService(db)
    sent_count = 0
    errors = []
    shared_ids = set(data_scope.get_shared_ids(ENTITY_TYPE_LEADS))
    can_see_all = data_scope.can_see_all()

    for lead_id in request_data.lead_ids:
        service = LeadService(db)
        lead = await service.get_by_id(lead_id)
        if not lead or not lead.email:
            errors.append({"lead_id": lead_id, "error": "Lead not found or no email"})
            continue

        if not can_see_all and lead.owner_id != current_user.id and lead.id not in shared_ids:
            # Don't reveal whether the lead exists; treat as inaccessible.
            errors.append({"lead_id": lead_id, "error": "Lead not found or no email"})
            continue

        variables = {
            "first_name": lead.first_name or "",
            "last_name": lead.last_name or "",
            "full_name": lead.full_name,
            "email": lead.email or "",
            "company_name": lead.company_name or "",
        }
        body = render_template(request_data.body_template, variables)
        subject = render_template(request_data.subject, variables, is_html=False)

        await email_service.queue_email(
            to_email=lead.email,
            subject=subject,
            body=body,
            sent_by_id=current_user.id,
            entity_type="leads",
            entity_id=lead.id,
        )
        sent_count += 1

    return {
        "sent_count": sent_count,
        "errors": errors,
        "total_requested": len(request_data.lead_ids),
    }


@router.post("/{lead_id}/move")
async def move_lead(
    lead_id: int,
    request: MoveLeadRequest,
    current_user: CurrentUser,
    db: DBSession,
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
):
    """Move a lead to a different pipeline stage with status sync.

    When moved to a Won stage, auto-converts the lead to Contact + Opportunity.
    """
    # Get the lead
    service = LeadService(db)
    lead = await get_entity_or_404(service, lead_id, EntityNames.LEAD)
    check_record_access_or_shared(
        lead, current_user, data_scope.role_name,
        shared_entity_ids=data_scope.get_shared_ids(ENTITY_TYPE_LEADS),
    )

    # Verify the new stage exists and is a lead stage
    stage_result = await db.execute(
        select(PipelineStage).where(PipelineStage.id == request.new_stage_id)
    )
    stage = stage_result.scalar_one_or_none()

    if not stage:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail=f"Pipeline stage {request.new_stage_id} not found",
        )

    if stage.pipeline_type != "lead":
        raise HTTPException(
            status_code=400,
            detail="Cannot move lead to a non-lead pipeline stage",
        )

    # Move lead to new stage
    lead.pipeline_stage_id = request.new_stage_id

    # Sync status based on stage
    if stage.is_won:
        lead.status = "converted"
    elif stage.is_lost:
        lead.status = "lost"
    else:
        # Map by stage order
        order_status_map = {1: "new", 2: "contacted", 3: "qualified", 4: "negotiation"}
        lead.status = order_status_map.get(stage.order, "qualified")

    await db.flush()
    await db.refresh(lead)

    # Auto-convert when moved to a Won stage
    conversion_info = None
    if stage.is_won and not lead.converted_contact_id and not lead.converted_opportunity_id:
        # Find the first opportunity pipeline stage (order=1, pipeline_type="opportunity")
        first_opp_stage_result = await db.execute(
            select(PipelineStage)
            .where(PipelineStage.pipeline_type == "opportunity")
            .where(PipelineStage.is_active == True)
            .order_by(PipelineStage.order)
            .limit(1)
        )
        first_opp_stage = first_opp_stage_result.scalar_one_or_none()

        if first_opp_stage:
            converter = LeadConverter(db)
            contact, company, opportunity = await converter.full_conversion(
                lead=lead,
                user_id=current_user.id,
                pipeline_stage_id=first_opp_stage.id,
                create_company=bool(lead.company_name),
            )
            await db.flush()
            await db.refresh(lead)

            conversion_info = {
                "converted": True,
                "contact_id": contact.id,
                "company_id": company.id if company else None,
                "opportunity_id": opportunity.id,
            }

    lead_response = await _build_lead_response(service, lead)
    response_dict = lead_response.model_dump()
    if conversion_info:
        response_dict["conversion"] = conversion_info
    return response_dict


@router.get("/{lead_id}", response_model=LeadResponse)
async def get_lead(
    lead_id: int,
    current_user: CurrentUser,
    db: DBSession,
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
):
    """Get a lead by ID."""
    service = LeadService(db)
    lead = await get_entity_or_404(service, lead_id, EntityNames.LEAD)
    check_record_access_or_shared(
        lead, current_user, data_scope.role_name,
        shared_entity_ids=data_scope.get_shared_ids(ENTITY_TYPE_LEADS),
    )
    return await _build_lead_response(service, lead)


@router.patch("/{lead_id}", response_model=LeadResponse)
async def update_lead(
    lead_id: int,
    lead_data: LeadUpdate,
    request: Request,
    current_user: CurrentUser,
    db: DBSession,
):
    """Update a lead."""
    service = LeadService(db)
    lead = await get_entity_or_404(service, lead_id, EntityNames.LEAD)
    check_ownership(lead, current_user, EntityNames.LEAD)

    old_owner_id = lead.owner_id

    update_fields = list(lead_data.model_dump(exclude_unset=True).keys())
    old_data = snapshot_entity(lead, update_fields)

    try:
        updated_lead = await service.update(lead, lead_data, current_user.id)
    except LeadValidationError as exc:
        # Catch the sentinel only — broader `except ValueError` would
        # swallow genuine bugs from filter/score paths.
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST, detail=str(exc),
        ) from exc

    # Update embedding for semantic search
    try:
        content = build_lead_embedding_content(updated_lead)
        await store_entity_embedding(db, "lead", updated_lead.id, content)
    except Exception as e:
        logger.warning("Failed to store embedding: %s", e)

    new_data = snapshot_entity(updated_lead, update_fields)
    ip_address = get_client_ip(request)
    await audit_entity_update(db, "lead", updated_lead.id, current_user.id, old_data, new_data, ip_address)

    await emit(LEAD_UPDATED, {
        "entity_id": updated_lead.id,
        "entity_type": "lead",
        "user_id": current_user.id,
        "data": {"first_name": updated_lead.first_name, "last_name": updated_lead.last_name, "email": updated_lead.email, "status": updated_lead.status},
    })

    if updated_lead.owner_id and updated_lead.owner_id != old_owner_id:
        await notify_on_assignment(db, updated_lead.owner_id, "leads", updated_lead.id, updated_lead.full_name)

    return await _build_lead_response(service, updated_lead)


@router.delete("/{lead_id}", status_code=HTTPStatus.NO_CONTENT)
async def delete_lead(
    lead_id: int,
    request: Request,
    current_user: CurrentUser,
    db: DBSession,
):
    """Delete a lead."""
    service = LeadService(db)
    lead = await get_entity_or_404(service, lead_id, EntityNames.LEAD)
    check_ownership(lead, current_user, EntityNames.LEAD)

    ip_address = get_client_ip(request)
    await audit_entity_delete(db, "lead", lead.id, current_user.id, ip_address)

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
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
):
    """Convert a lead to a contact."""
    service = LeadService(db)
    lead = await get_entity_or_404(service, lead_id, EntityNames.LEAD)
    check_record_access_or_shared(
        lead, current_user, data_scope.role_name,
        shared_entity_ids=data_scope.get_shared_ids(ENTITY_TYPE_LEADS),
    )

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
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
):
    """Convert a lead to an opportunity."""
    service = LeadService(db)
    lead = await get_entity_or_404(service, lead_id, EntityNames.LEAD)
    check_record_access_or_shared(
        lead, current_user, data_scope.role_name,
        shared_entity_ids=data_scope.get_shared_ids(ENTITY_TYPE_LEADS),
    )

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
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
):
    """Full lead conversion: Lead -> Contact + Company + Opportunity."""
    service = LeadService(db)
    lead = await get_entity_or_404(service, lead_id, EntityNames.LEAD)
    check_record_access_or_shared(
        lead, current_user, data_scope.role_name,
        shared_entity_ids=data_scope.get_shared_ids(ENTITY_TYPE_LEADS),
    )

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
@router.get("/sources/", response_model=list[LeadSourceResponse])
async def list_sources(
    current_user: CurrentUser,
    db: DBSession,
    response: Response,
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
    response.headers["Cache-Control"] = "public, max-age=300"
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


@router.patch("/sources/{source_id}", response_model=LeadSourceResponse)
async def update_source(
    source_id: int,
    source_data: LeadSourceUpdate,
    current_user: CurrentUser,
    db: DBSession,
):
    """Update a lead source."""
    service = LeadService(db)
    source = await service.update_source(source_id, source_data)
    if source is None:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Lead source not found"
        )
    invalidate_lead_sources_cache()
    return source


@router.delete("/sources/{source_id}", status_code=HTTPStatus.NO_CONTENT)
async def delete_source(
    source_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Delete a lead source. Fails with 409 if any leads still reference it."""
    service = LeadService(db)
    source = await service.get_source_by_id(source_id)
    if source is None:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Lead source not found"
        )
    lead_count = await service.count_leads_by_source(source_id)
    if lead_count > 0:
        raise HTTPException(
            status_code=HTTPStatus.CONFLICT,
            detail=(
                f"Cannot delete source '{source.name}': {lead_count} lead(s) still "
                "reference it. Reassign or delete those leads first."
            ),
        )
    await service.delete_source(source)
    invalidate_lead_sources_cache()
