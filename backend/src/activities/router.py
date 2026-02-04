"""Activity API routes."""

from typing import Annotated, Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_db
from src.auth.models import User
from src.auth.dependencies import get_current_active_user
from src.activities.models import Activity
from src.activities.schemas import (
    ActivityCreate,
    ActivityUpdate,
    ActivityResponse,
    ActivityListResponse,
    TimelineResponse,
    TimelineItem,
    CompleteActivityRequest,
)
from src.activities.service import ActivityService
from src.activities.timeline import ActivityTimeline

router = APIRouter(prefix="/api/activities", tags=["activities"])


@router.get("", response_model=ActivityListResponse)
async def list_activities(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    activity_type: Optional[str] = None,
    owner_id: Optional[int] = None,
    assigned_to_id: Optional[int] = None,
    is_completed: Optional[bool] = None,
    priority: Optional[str] = None,
):
    """List activities with pagination and filters."""
    service = ActivityService(db)

    activities, total = await service.get_list(
        page=page,
        page_size=page_size,
        entity_type=entity_type,
        entity_id=entity_id,
        activity_type=activity_type,
        owner_id=owner_id,
        assigned_to_id=assigned_to_id,
        is_completed=is_completed,
        priority=priority,
    )

    pages = (total + page_size - 1) // page_size

    return ActivityListResponse(
        items=[ActivityResponse.model_validate(a) for a in activities],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


@router.post("", response_model=ActivityResponse, status_code=status.HTTP_201_CREATED)
async def create_activity(
    activity_data: ActivityCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Create a new activity."""
    service = ActivityService(db)
    activity = await service.create(activity_data, current_user.id)
    return ActivityResponse.model_validate(activity)


@router.get("/my-tasks", response_model=List[ActivityResponse])
async def get_my_tasks(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    include_completed: bool = False,
    limit: int = Query(50, ge=1, le=100),
):
    """Get tasks assigned to or owned by current user."""
    service = ActivityService(db)
    tasks = await service.get_my_tasks(
        user_id=current_user.id,
        include_completed=include_completed,
        limit=limit,
    )
    return [ActivityResponse.model_validate(t) for t in tasks]


@router.get("/timeline/entity/{entity_type}/{entity_id}", response_model=TimelineResponse)
async def get_entity_timeline(
    entity_type: str,
    entity_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(50, ge=1, le=100),
    activity_types: Optional[str] = None,
):
    """Get activity timeline for an entity."""
    timeline = ActivityTimeline(db)

    parsed_types = None
    if activity_types:
        parsed_types = activity_types.split(",")

    items = await timeline.get_entity_timeline(
        entity_type=entity_type,
        entity_id=entity_id,
        limit=limit,
        activity_types=parsed_types,
    )

    return TimelineResponse(items=[TimelineItem(**item) for item in items])


@router.get("/timeline/user", response_model=TimelineResponse)
async def get_user_timeline(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(50, ge=1, le=100),
    include_assigned: bool = True,
    activity_types: Optional[str] = None,
):
    """Get activity timeline for current user."""
    timeline = ActivityTimeline(db)

    parsed_types = None
    if activity_types:
        parsed_types = activity_types.split(",")

    items = await timeline.get_user_timeline(
        user_id=current_user.id,
        limit=limit,
        include_assigned=include_assigned,
        activity_types=parsed_types,
    )

    return TimelineResponse(items=[TimelineItem(**item) for item in items])


@router.get("/upcoming", response_model=TimelineResponse)
async def get_upcoming_activities(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    days_ahead: int = Query(7, ge=1, le=30),
    limit: int = Query(20, ge=1, le=100),
):
    """Get upcoming scheduled activities."""
    timeline = ActivityTimeline(db)
    items = await timeline.get_upcoming_activities(
        user_id=current_user.id,
        days_ahead=days_ahead,
        limit=limit,
    )
    return TimelineResponse(items=[TimelineItem(**item) for item in items])


@router.get("/overdue", response_model=TimelineResponse)
async def get_overdue_activities(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(20, ge=1, le=100),
):
    """Get overdue tasks."""
    timeline = ActivityTimeline(db)
    items = await timeline.get_overdue_tasks(
        user_id=current_user.id,
        limit=limit,
    )
    return TimelineResponse(items=[TimelineItem(**item) for item in items])


@router.get("/{activity_id}", response_model=ActivityResponse)
async def get_activity(
    activity_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Get an activity by ID."""
    service = ActivityService(db)
    activity = await service.get_by_id(activity_id)

    if not activity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Activity not found",
        )

    return ActivityResponse.model_validate(activity)


@router.patch("/{activity_id}", response_model=ActivityResponse)
async def update_activity(
    activity_id: int,
    activity_data: ActivityUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Update an activity."""
    service = ActivityService(db)
    activity = await service.get_by_id(activity_id)

    if not activity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Activity not found",
        )

    updated_activity = await service.update(activity, activity_data, current_user.id)
    return ActivityResponse.model_validate(updated_activity)


@router.post("/{activity_id}/complete", response_model=ActivityResponse)
async def complete_activity(
    activity_id: int,
    request: CompleteActivityRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Mark an activity as completed."""
    service = ActivityService(db)
    activity = await service.get_by_id(activity_id)

    if not activity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Activity not found",
        )

    completed_activity = await service.complete(activity, current_user.id, request.notes)
    return ActivityResponse.model_validate(completed_activity)


@router.delete("/{activity_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_activity(
    activity_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Delete an activity."""
    service = ActivityService(db)
    activity = await service.get_by_id(activity_id)

    if not activity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Activity not found",
        )

    await service.delete(activity)
