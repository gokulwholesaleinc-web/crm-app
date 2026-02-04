"""Opportunity API routes."""

from typing import Annotated, Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_db
from src.auth.models import User
from src.auth.dependencies import get_current_active_user
from src.opportunities.models import Opportunity, PipelineStage
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

router = APIRouter(prefix="/api/opportunities", tags=["opportunities"])


# Pipeline Stages endpoints
@router.get("/stages", response_model=List[PipelineStageResponse])
async def list_stages(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    active_only: bool = True,
):
    """List all pipeline stages."""
    service = PipelineStageService(db)
    stages = await service.get_all(active_only=active_only)
    return stages


@router.post("/stages", response_model=PipelineStageResponse, status_code=status.HTTP_201_CREATED)
async def create_stage(
    stage_data: PipelineStageCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Create a new pipeline stage."""
    service = PipelineStageService(db)
    stage = await service.create(stage_data)
    return stage


@router.patch("/stages/{stage_id}", response_model=PipelineStageResponse)
async def update_stage(
    stage_id: int,
    stage_data: PipelineStageUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Update a pipeline stage."""
    service = PipelineStageService(db)
    stage = await service.get_by_id(stage_id)

    if not stage:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pipeline stage not found",
        )

    updated_stage = await service.update(stage, stage_data)
    return updated_stage


@router.post("/stages/reorder", response_model=List[PipelineStageResponse])
async def reorder_stages(
    stage_orders: List[dict],  # [{id: int, order: int}, ...]
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Reorder pipeline stages."""
    service = PipelineStageService(db)
    stages = await service.reorder(stage_orders)
    return stages


# Kanban/Pipeline view
@router.get("/kanban", response_model=KanbanResponse)
async def get_kanban_view(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    owner_id: Optional[int] = None,
):
    """Get Kanban board view of pipeline."""
    manager = PipelineManager(db)
    kanban_data = await manager.get_kanban_data(owner_id=owner_id)

    return KanbanResponse(
        stages=[KanbanStage(**stage) for stage in kanban_data]
    )


@router.post("/{opportunity_id}/move", response_model=OpportunityResponse)
async def move_opportunity(
    opportunity_id: int,
    request: MoveOpportunityRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
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
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )

    opp_service = OpportunityService(db)
    tags = await opp_service.get_opportunity_tags(opportunity.id)
    response = OpportunityResponse.model_validate(opportunity)
    response_dict = response.model_dump()
    response_dict["tags"] = [TagBrief.model_validate(t) for t in tags]

    return OpportunityResponse(**response_dict)


# Forecasting endpoints
@router.get("/forecast", response_model=ForecastResponse)
async def get_forecast(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
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
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    owner_id: Optional[int] = None,
):
    """Get pipeline summary."""
    forecaster = RevenueForecast(db)
    summary = await forecaster.get_pipeline_summary(owner_id=owner_id)
    return summary


# Opportunity CRUD endpoints
@router.get("", response_model=OpportunityListResponse)
async def list_opportunities(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    pipeline_stage_id: Optional[int] = None,
    contact_id: Optional[int] = None,
    company_id: Optional[int] = None,
    owner_id: Optional[int] = None,
    tag_ids: Optional[str] = None,
):
    """List opportunities with pagination and filters."""
    service = OpportunityService(db)

    parsed_tag_ids = None
    if tag_ids:
        parsed_tag_ids = [int(x) for x in tag_ids.split(",")]

    opportunities, total = await service.get_list(
        page=page,
        page_size=page_size,
        search=search,
        pipeline_stage_id=pipeline_stage_id,
        contact_id=contact_id,
        company_id=company_id,
        owner_id=owner_id,
        tag_ids=parsed_tag_ids,
    )

    opp_responses = []
    for opp in opportunities:
        tags = await service.get_opportunity_tags(opp.id)
        opp_dict = OpportunityResponse.model_validate(opp).model_dump()
        opp_dict["tags"] = [TagBrief.model_validate(t) for t in tags]
        opp_responses.append(OpportunityResponse(**opp_dict))

    pages = (total + page_size - 1) // page_size

    return OpportunityListResponse(
        items=opp_responses,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


@router.post("", response_model=OpportunityResponse, status_code=status.HTTP_201_CREATED)
async def create_opportunity(
    opp_data: OpportunityCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Create a new opportunity."""
    service = OpportunityService(db)
    opportunity = await service.create(opp_data, current_user.id)

    tags = await service.get_opportunity_tags(opportunity.id)
    response = OpportunityResponse.model_validate(opportunity)
    response_dict = response.model_dump()
    response_dict["tags"] = [TagBrief.model_validate(t) for t in tags]

    return OpportunityResponse(**response_dict)


@router.get("/{opportunity_id}", response_model=OpportunityResponse)
async def get_opportunity(
    opportunity_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Get an opportunity by ID."""
    service = OpportunityService(db)
    opportunity = await service.get_by_id(opportunity_id)

    if not opportunity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Opportunity not found",
        )

    tags = await service.get_opportunity_tags(opportunity.id)
    response = OpportunityResponse.model_validate(opportunity)
    response_dict = response.model_dump()
    response_dict["tags"] = [TagBrief.model_validate(t) for t in tags]

    return OpportunityResponse(**response_dict)


@router.patch("/{opportunity_id}", response_model=OpportunityResponse)
async def update_opportunity(
    opportunity_id: int,
    opp_data: OpportunityUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Update an opportunity."""
    service = OpportunityService(db)
    opportunity = await service.get_by_id(opportunity_id)

    if not opportunity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Opportunity not found",
        )

    updated_opp = await service.update(opportunity, opp_data, current_user.id)

    tags = await service.get_opportunity_tags(updated_opp.id)
    response = OpportunityResponse.model_validate(updated_opp)
    response_dict = response.model_dump()
    response_dict["tags"] = [TagBrief.model_validate(t) for t in tags]

    return OpportunityResponse(**response_dict)


@router.delete("/{opportunity_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_opportunity(
    opportunity_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Delete an opportunity."""
    service = OpportunityService(db)
    opportunity = await service.get_by_id(opportunity_id)

    if not opportunity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Opportunity not found",
        )

    await service.delete(opportunity)
