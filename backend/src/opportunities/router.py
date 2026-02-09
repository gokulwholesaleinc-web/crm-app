"""Opportunity API routes."""

import logging
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query
from src.core.constants import HTTPStatus, EntityNames
from src.core.router_utils import (
    DBSession,
    CurrentUser,
    parse_tag_ids,
    get_entity_or_404,
    calculate_pages,
    check_ownership,
)
from src.core.cache import (
    cached_fetch,
    CACHE_PIPELINE_STAGES,
    invalidate_pipeline_stages_cache,
)
from src.opportunities.schemas import (
    OpportunityCreate,
    OpportunityUpdate,
    OpportunityResponse,
    OpportunityListResponse,
    PipelineStageCreate,
    PipelineStageUpdate,
    PipelineStageResponse,
    KanbanResponse,
    KanbanStage,
    MoveOpportunityRequest,
    ForecastResponse,
    PipelineSummaryResponse,
    TagBrief,
)
from src.opportunities.service import OpportunityService, PipelineStageService
from src.opportunities.pipeline import PipelineManager
from src.opportunities.forecasting import RevenueForecast
from src.ai.embedding_hooks import (
    store_entity_embedding,
    delete_entity_embedding,
    build_opportunity_embedding_content,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/opportunities", tags=["opportunities"])


async def _build_opportunity_response(
    service: OpportunityService, opportunity
) -> OpportunityResponse:
    """Build an OpportunityResponse with tags."""
    tags = await service.get_tags(opportunity.id)
    response_dict = OpportunityResponse.model_validate(opportunity).model_dump()
    response_dict["tags"] = [TagBrief.model_validate(t) for t in tags]
    return OpportunityResponse(**response_dict)


# Pipeline Stages endpoints
@router.get("/stages", response_model=List[PipelineStageResponse])
async def list_stages(
    current_user: CurrentUser,
    db: DBSession,
    active_only: bool = True,
):
    """List all pipeline stages (cached for 5 minutes)."""
    service = PipelineStageService(db)

    async def fetch_stages():
        stages = await service.get_all(active_only=active_only)
        # Convert to dicts for caching (ORM objects can't be cached across sessions)
        return [PipelineStageResponse.model_validate(s).model_dump() for s in stages]

    cached_stages = await cached_fetch(
        CACHE_PIPELINE_STAGES,
        f"stages:{active_only}",
        fetch_stages,
    )
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


@router.post("/stages/reorder", response_model=List[PipelineStageResponse])
async def reorder_stages(
    stage_orders: List[dict],  # [{id: int, order: int}, ...]
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
    owner_id: Optional[int] = None,
):
    """Get Kanban board view of pipeline."""
    manager = PipelineManager(db)
    kanban_data = await manager.get_kanban_data(owner_id=owner_id)

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
        )

    opp_service = OpportunityService(db)
    return await _build_opportunity_response(opp_service, opportunity)


# Forecasting endpoints
@router.get("/forecast", response_model=ForecastResponse)
async def get_forecast(
    current_user: CurrentUser,
    db: DBSession,
    months_ahead: int = Query(6, ge=1, le=12),
    owner_id: Optional[int] = None,
):
    """Get revenue forecast."""
    forecaster = RevenueForecast(db)
    forecast = await forecaster.get_forecast(
        months_ahead=months_ahead,
        owner_id=owner_id,
    )
    return forecast


@router.get("/pipeline-summary", response_model=PipelineSummaryResponse)
async def get_pipeline_summary(
    current_user: CurrentUser,
    db: DBSession,
    owner_id: Optional[int] = None,
):
    """Get pipeline summary."""
    forecaster = RevenueForecast(db)
    summary = await forecaster.get_pipeline_summary(owner_id=owner_id)
    return summary


# Opportunity CRUD endpoints
@router.get("", response_model=OpportunityListResponse)
async def list_opportunities(
    current_user: CurrentUser,
    db: DBSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    pipeline_stage_id: Optional[int] = None,
    contact_id: Optional[int] = None,
    company_id: Optional[int] = None,
    owner_id: Optional[int] = None,
    tag_ids: Optional[str] = None,
    filters: Optional[str] = None,
):
    """List opportunities with pagination and filters."""
    import json as _json
    parsed_filters = _json.loads(filters) if filters else None

    # Auto-scope to current user's data by default
    effective_owner_id = owner_id
    if effective_owner_id is None:
        effective_owner_id = current_user.id

    service = OpportunityService(db)

    opportunities, total = await service.get_list(
        page=page,
        page_size=page_size,
        search=search,
        pipeline_stage_id=pipeline_stage_id,
        contact_id=contact_id,
        company_id=company_id,
        owner_id=effective_owner_id,
        tag_ids=parse_tag_ids(tag_ids),
        filters=parsed_filters,
    )

    opp_responses = [
        await _build_opportunity_response(service, opp) for opp in opportunities
    ]

    return OpportunityListResponse(
        items=opp_responses,
        total=total,
        page=page,
        page_size=page_size,
        pages=calculate_pages(total, page_size),
    )


@router.post("", response_model=OpportunityResponse, status_code=HTTPStatus.CREATED)
async def create_opportunity(
    opp_data: OpportunityCreate,
    current_user: CurrentUser,
    db: DBSession,
):
    """Create a new opportunity."""
    service = OpportunityService(db)
    opportunity = await service.create(opp_data, current_user.id)

    # Generate embedding for semantic search
    try:
        content = build_opportunity_embedding_content(opportunity)
        await store_entity_embedding(db, "opportunity", opportunity.id, content)
    except Exception as e:
        logger.warning("Failed to store embedding: %s", e)

    return await _build_opportunity_response(service, opportunity)


@router.get("/{opportunity_id}", response_model=OpportunityResponse)
async def get_opportunity(
    opportunity_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Get an opportunity by ID."""
    service = OpportunityService(db)
    opportunity = await get_entity_or_404(
        service, opportunity_id, EntityNames.OPPORTUNITY
    )
    return await _build_opportunity_response(service, opportunity)


@router.patch("/{opportunity_id}", response_model=OpportunityResponse)
async def update_opportunity(
    opportunity_id: int,
    opp_data: OpportunityUpdate,
    current_user: CurrentUser,
    db: DBSession,
):
    """Update an opportunity."""
    service = OpportunityService(db)
    opportunity = await get_entity_or_404(
        service, opportunity_id, EntityNames.OPPORTUNITY
    )
    check_ownership(opportunity, current_user, EntityNames.OPPORTUNITY)
    updated_opp = await service.update(opportunity, opp_data, current_user.id)

    # Update embedding for semantic search
    try:
        content = build_opportunity_embedding_content(updated_opp)
        await store_entity_embedding(db, "opportunity", updated_opp.id, content)
    except Exception as e:
        logger.warning("Failed to store embedding: %s", e)

    return await _build_opportunity_response(service, updated_opp)


@router.delete("/{opportunity_id}", status_code=HTTPStatus.NO_CONTENT)
async def delete_opportunity(
    opportunity_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Delete an opportunity."""
    service = OpportunityService(db)
    opportunity = await get_entity_or_404(
        service, opportunity_id, EntityNames.OPPORTUNITY
    )
    check_ownership(opportunity, current_user, EntityNames.OPPORTUNITY)

    # Delete embedding before deleting entity
    await delete_entity_embedding(db, "opportunity", opportunity.id)

    await service.delete(opportunity)
