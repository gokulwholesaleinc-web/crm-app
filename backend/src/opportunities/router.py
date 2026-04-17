"""Opportunity API routes."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy import select

from src.ai.embedding_hooks import (
    build_opportunity_embedding_content,
    delete_entity_embedding,
    store_entity_embedding,
)
from src.audit.utils import (
    audit_entity_create,
    audit_entity_delete,
    audit_entity_update,
    snapshot_entity,
)
from src.core.cache import (
    CACHE_PIPELINE_STAGES,
    cached_fetch,
    invalidate_pipeline_stages_cache,
)
from src.core.constants import ENTITY_TYPE_OPPORTUNITIES, EntityNames, HTTPStatus
from src.core.data_scope import DataScope, check_record_access_or_shared, get_data_scope
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
)
from src.events.service import (
    OPPORTUNITY_CREATED,
    OPPORTUNITY_STAGE_CHANGED,
    OPPORTUNITY_UPDATED,
    emit,
)
from src.notifications.service import notify_on_assignment, notify_on_stage_change
from src.opportunities.forecasting import RevenueForecast
from src.opportunities.models import Opportunity, PipelineStage
from src.opportunities.pipeline import PipelineManager
from src.opportunities.schemas import (
    ForecastResponse,
    KanbanResponse,
    KanbanStage,
    MoveOpportunityRequest,
    OpportunityCreate,
    OpportunityListResponse,
    OpportunityResponse,
    OpportunityUpdate,
    PipelineStageCreate,
    PipelineStageResponse,
    PipelineStageUpdate,
    PipelineSummaryResponse,
    TagBrief,
)
from src.opportunities.service import OpportunityService, PipelineStageService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/opportunities", tags=["opportunities"])


async def _build_opportunity_response(
    service: OpportunityService, opportunity
) -> OpportunityResponse:
    return await build_response_with_tags(service, opportunity, OpportunityResponse, TagBrief)


# Pipeline Stages endpoints
@router.get("/stages", response_model=list[PipelineStageResponse])
async def list_stages(
    current_user: CurrentUser,
    db: DBSession,
    response: Response,
    active_only: bool = True,
    pipeline_type: str | None = None,
):
    """List all pipeline stages (cached for 5 minutes)."""
    service = PipelineStageService(db)

    async def fetch_stages():
        stages = await service.get_all(active_only=active_only, pipeline_type=pipeline_type)
        # Convert to dicts for caching (ORM objects can't be cached across sessions)
        return [PipelineStageResponse.model_validate(s).model_dump() for s in stages]

    cached_stages = await cached_fetch(
        CACHE_PIPELINE_STAGES,
        f"stages:{active_only}:{pipeline_type}",
        fetch_stages,
    )
    response.headers["Cache-Control"] = "public, max-age=300"
    return cached_stages


@router.post("/stages", response_model=PipelineStageResponse, status_code=HTTPStatus.CREATED)
async def create_stage(
    stage_data: PipelineStageCreate,
    current_user: CurrentUser,
    db: DBSession,
):
    """Create a new pipeline stage."""
    service = PipelineStageService(db)
    stage = await service.create(stage_data)
    # Invalidate cache since we added a new stage
    invalidate_pipeline_stages_cache()
    return stage


@router.patch("/stages/{stage_id}", response_model=PipelineStageResponse)
async def update_stage(
    stage_id: int,
    stage_data: PipelineStageUpdate,
    current_user: CurrentUser,
    db: DBSession,
):
    """Update a pipeline stage."""
    service = PipelineStageService(db)
    stage = await get_entity_or_404(service, stage_id, EntityNames.PIPELINE_STAGE)
    updated_stage = await service.update(stage, stage_data)
    # Invalidate cache since we updated a stage
    invalidate_pipeline_stages_cache()
    return updated_stage


@router.delete("/stages/{stage_id}", status_code=HTTPStatus.NO_CONTENT)
async def delete_stage(
    stage_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Delete a pipeline stage. Fails if opportunities still reference it."""
    service = PipelineStageService(db)
    stage = await get_entity_or_404(service, stage_id, EntityNames.PIPELINE_STAGE)

    # Check if any opportunities reference this stage
    from sqlalchemy import func as sa_func
    count_result = await db.execute(
        select(sa_func.count()).select_from(Opportunity).where(Opportunity.pipeline_stage_id == stage_id)
    )
    count = count_result.scalar() or 0
    if count > 0:
        raise HTTPException(
            status_code=HTTPStatus.CONFLICT,
            detail=f"Cannot delete stage '{stage.name}': {count} opportunity(ies) still use it. Move them first.",
        )

    await service.delete(stage)
    invalidate_pipeline_stages_cache()


@router.post("/stages/reorder", response_model=list[PipelineStageResponse])
async def reorder_stages(
    stage_orders: list[dict],  # [{id: int, order: int}, ...]
    current_user: CurrentUser,
    db: DBSession,
):
    """Reorder pipeline stages."""
    service = PipelineStageService(db)
    stages = await service.reorder(stage_orders)
    # Invalidate cache since we reordered stages
    invalidate_pipeline_stages_cache()
    return stages


# Kanban/Pipeline view
@router.get("/kanban", response_model=KanbanResponse)
async def get_kanban_view(
    current_user: CurrentUser,
    db: DBSession,
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
    owner_id: int | None = None,
):
    """Get Kanban board view of pipeline.

    Sales reps can only see their own kanban; admin/manager can pass
    owner_id to view another user's board. Spoofed owner_id from a
    sales_rep is ignored and collapsed back to the caller.
    """
    resolved_owner_id = effective_owner_id(data_scope, owner_id)
    if resolved_owner_id is None and not data_scope.can_see_all():
        resolved_owner_id = current_user.id
    manager = PipelineManager(db)
    kanban_data = await manager.get_kanban_data(owner_id=resolved_owner_id)

    return KanbanResponse(stages=[KanbanStage(**stage) for stage in kanban_data])


@router.post("/{opportunity_id}/move", response_model=OpportunityResponse)
async def move_opportunity(
    opportunity_id: int,
    request: MoveOpportunityRequest,
    current_user: CurrentUser,
    db: DBSession,
):
    """Move an opportunity to a different pipeline stage."""
    manager = PipelineManager(db)

    try:
        opportunity = await manager.move_opportunity(
            opportunity_id=opportunity_id,
            new_stage_id=request.new_stage_id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail=str(e),
        ) from e

    opp_service = OpportunityService(db)
    return await _build_opportunity_response(opp_service, opportunity)


# Forecasting endpoints
@router.get("/forecast", response_model=ForecastResponse)
async def get_forecast(
    current_user: CurrentUser,
    db: DBSession,
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
    months_ahead: int = Query(6, ge=1, le=12),
    owner_id: int | None = None,
):
    """Get revenue forecast. Sales reps cannot spoof owner_id."""
    resolved_owner_id = effective_owner_id(data_scope, owner_id)
    if resolved_owner_id is None and not data_scope.can_see_all():
        resolved_owner_id = current_user.id
    forecaster = RevenueForecast(db)
    forecast = await forecaster.get_forecast(
        months_ahead=months_ahead,
        owner_id=resolved_owner_id,
    )
    return forecast


@router.get("/pipeline-summary", response_model=PipelineSummaryResponse)
async def get_pipeline_summary(
    current_user: CurrentUser,
    db: DBSession,
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
    owner_id: int | None = None,
):
    """Get pipeline summary. Sales reps cannot spoof owner_id."""
    resolved_owner_id = effective_owner_id(data_scope, owner_id)
    if resolved_owner_id is None and not data_scope.can_see_all():
        resolved_owner_id = current_user.id
    forecaster = RevenueForecast(db)
    summary = await forecaster.get_pipeline_summary(owner_id=resolved_owner_id)
    return summary


# Opportunity CRUD endpoints
@router.get("", response_model=OpportunityListResponse)
async def list_opportunities(
    current_user: CurrentUser,
    db: DBSession,
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = None,
    pipeline_stage_id: int | None = None,
    contact_id: int | None = None,
    company_id: int | None = None,
    owner_id: int | None = None,
    tag_ids: str | None = None,
    filters: str | None = None,
):
    """List opportunities with pagination and filters."""
    service = OpportunityService(db)

    opportunities, total = await service.get_list(
        page=page,
        page_size=page_size,
        search=search,
        pipeline_stage_id=pipeline_stage_id,
        contact_id=contact_id,
        company_id=company_id,
        owner_id=effective_owner_id(data_scope, owner_id),
        tag_ids=parse_tag_ids(tag_ids),
        filters=parse_json_filters(filters),
        shared_entity_ids=data_scope.get_shared_ids(ENTITY_TYPE_OPPORTUNITIES),
    )

    tags_map = await service.get_tags_for_entities([o.id for o in opportunities])

    return OpportunityListResponse(
        items=build_list_responses_with_tags(opportunities, tags_map, OpportunityResponse, TagBrief),
        total=total,
        page=page,
        page_size=page_size,
        pages=calculate_pages(total, page_size),
    )


@router.post("", response_model=OpportunityResponse, status_code=HTTPStatus.CREATED)
async def create_opportunity(
    opp_data: OpportunityCreate,
    request: Request,
    current_user: CurrentUser,
    db: DBSession,
):
    """Create a new opportunity."""
    # Validate stage type
    stage_result = await db.execute(
        select(PipelineStage).where(PipelineStage.id == opp_data.pipeline_stage_id)
    )
    stage = stage_result.scalar_one_or_none()
    if not stage or stage.pipeline_type != "opportunity":
        raise HTTPException(
            status_code=400,
            detail="Invalid pipeline stage for opportunity",
        )

    # Default owner to current user if not provided
    if opp_data.owner_id is None:
        opp_data.owner_id = current_user.id

    service = OpportunityService(db)
    opportunity = await service.create(opp_data, current_user.id)

    # Generate embedding for semantic search
    try:
        content = build_opportunity_embedding_content(opportunity)
        await store_entity_embedding(db, "opportunity", opportunity.id, content)
    except Exception as e:
        logger.warning("Failed to store embedding: %s", e)

    ip_address = request.client.host if request.client else None
    await audit_entity_create(db, "opportunity", opportunity.id, current_user.id, ip_address)

    await emit(OPPORTUNITY_CREATED, {
        "entity_id": opportunity.id,
        "entity_type": "opportunity",
        "user_id": current_user.id,
        "data": {"name": opportunity.name, "amount": opportunity.amount, "pipeline_stage_id": opportunity.pipeline_stage_id},
    })

    if opportunity.owner_id and opportunity.owner_id != current_user.id:
        await notify_on_assignment(db, opportunity.owner_id, "opportunities", opportunity.id, opportunity.name)

    return await _build_opportunity_response(service, opportunity)


@router.get("/{opportunity_id}", response_model=OpportunityResponse)
async def get_opportunity(
    opportunity_id: int,
    current_user: CurrentUser,
    db: DBSession,
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
):
    """Get an opportunity by ID."""
    service = OpportunityService(db)
    opportunity = await get_entity_or_404(
        service, opportunity_id, EntityNames.OPPORTUNITY
    )
    check_record_access_or_shared(
        opportunity, current_user, data_scope.role_name,
        shared_entity_ids=data_scope.get_shared_ids(ENTITY_TYPE_OPPORTUNITIES),
    )
    return await _build_opportunity_response(service, opportunity)


@router.patch("/{opportunity_id}", response_model=OpportunityResponse)
async def update_opportunity(
    opportunity_id: int,
    opp_data: OpportunityUpdate,
    request: Request,
    current_user: CurrentUser,
    db: DBSession,
):
    """Update an opportunity."""
    service = OpportunityService(db)
    opportunity = await get_entity_or_404(
        service, opportunity_id, EntityNames.OPPORTUNITY
    )
    check_ownership(opportunity, current_user, EntityNames.OPPORTUNITY)
    old_stage_id = opportunity.pipeline_stage_id
    old_stage_name = opportunity.pipeline_stage.name if opportunity.pipeline_stage else str(old_stage_id)
    old_owner_id = opportunity.owner_id

    update_fields = list(opp_data.model_dump(exclude_unset=True).keys())
    old_data = snapshot_entity(opportunity, update_fields)

    updated_opp = await service.update(opportunity, opp_data, current_user.id)

    # Update embedding for semantic search
    try:
        content = build_opportunity_embedding_content(updated_opp)
        await store_entity_embedding(db, "opportunity", updated_opp.id, content)
    except Exception as e:
        logger.warning("Failed to store embedding: %s", e)

    new_data = snapshot_entity(updated_opp, update_fields)
    ip_address = request.client.host if request.client else None
    await audit_entity_update(db, "opportunity", updated_opp.id, current_user.id, old_data, new_data, ip_address)

    await emit(OPPORTUNITY_UPDATED, {
        "entity_id": updated_opp.id,
        "entity_type": "opportunity",
        "user_id": current_user.id,
        "data": {"name": updated_opp.name, "amount": updated_opp.amount, "pipeline_stage_id": updated_opp.pipeline_stage_id},
    })

    if updated_opp.pipeline_stage_id != old_stage_id:
        await emit(OPPORTUNITY_STAGE_CHANGED, {
            "entity_id": updated_opp.id,
            "entity_type": "opportunity",
            "user_id": current_user.id,
            "data": {"name": updated_opp.name, "old_stage_id": old_stage_id, "new_stage_id": updated_opp.pipeline_stage_id},
        })

        new_stage_name = updated_opp.pipeline_stage.name if updated_opp.pipeline_stage else str(updated_opp.pipeline_stage_id)
        notify_user = updated_opp.owner_id or current_user.id
        await notify_on_stage_change(db, notify_user, "opportunities", updated_opp.id, updated_opp.name, old_stage_name, new_stage_name)

    if updated_opp.owner_id and updated_opp.owner_id != old_owner_id:
        await notify_on_assignment(db, updated_opp.owner_id, "opportunities", updated_opp.id, updated_opp.name)

    return await _build_opportunity_response(service, updated_opp)


@router.delete("/{opportunity_id}", status_code=HTTPStatus.NO_CONTENT)
async def delete_opportunity(
    opportunity_id: int,
    request: Request,
    current_user: CurrentUser,
    db: DBSession,
):
    """Delete an opportunity."""
    service = OpportunityService(db)
    opportunity = await get_entity_or_404(
        service, opportunity_id, EntityNames.OPPORTUNITY
    )
    check_ownership(opportunity, current_user, EntityNames.OPPORTUNITY)

    ip_address = request.client.host if request.client else None
    await audit_entity_delete(db, "opportunity", opportunity.id, current_user.id, ip_address)

    # Delete embedding before deleting entity
    await delete_entity_embedding(db, "opportunity", opportunity.id)

    await service.delete(opportunity)
