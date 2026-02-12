"""Activity API routes."""

from typing import Annotated, Optional, List
from fastapi import APIRouter, Depends, Query, Request
from src.core.constants import HTTPStatus, EntityNames, ENTITY_TYPE_ACTIVITIES
from src.core.router_utils import (
    DBSession,
    CurrentUser,
    parse_comma_separated,
    get_entity_or_404,
    calculate_pages,
    check_ownership,
)
from src.core.data_scope import DataScope, get_data_scope, check_record_access_or_shared
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
from src.audit.utils import audit_entity_create, audit_entity_update, audit_entity_delete, snapshot_entity
from src.events.service import emit, ACTIVITY_CREATED

router = APIRouter(prefix="/api/activities", tags=["activities"])


@router.get("/calendar")
async def get_calendar_activities(
    current_user: CurrentUser,
    db: DBSession,
    start_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(..., description="End date (YYYY-MM-DD)"),
    activity_type: Optional[str] = None,
    owner_id: Optional[int] = None,
):
    """Get activities grouped by date for calendar view."""
    from datetime import date as date_type
    from sqlalchemy import select, or_, and_, func as sa_func
    from collections import defaultdict

    start = date_type.fromisoformat(start_date)
    end = date_type.fromisoformat(end_date)

    from src.activities.models import Activity as ActivityModel

    query = select(ActivityModel)
    filters = []

    # Use func.date() for cross-database compatibility (works in both PostgreSQL and SQLite)
    scheduled_filter = and_(
        ActivityModel.scheduled_at.isnot(None),
        sa_func.date(ActivityModel.scheduled_at) >= start.isoformat(),
        sa_func.date(ActivityModel.scheduled_at) <= end.isoformat(),
    )
    due_filter = and_(
        ActivityModel.due_date.isnot(None),
        ActivityModel.due_date >= start,
        ActivityModel.due_date <= end,
    )
    filters.append(or_(scheduled_filter, due_filter))

    if activity_type:
        filters.append(ActivityModel.activity_type == activity_type)
    # Auto-scope to current user's data by default
    effective_owner_id = owner_id if owner_id is not None else current_user.id
    filters.append(ActivityModel.owner_id == effective_owner_id)

    query = query.where(and_(*filters))
    result = await db.execute(query)
    activities = result.scalars().all()

    dates = defaultdict(list)
    for act in activities:
        if act.scheduled_at:
            act_date = act.scheduled_at.date() if hasattr(act.scheduled_at, 'date') else act.scheduled_at
        elif act.due_date:
            act_date = act.due_date
        else:
            continue

        date_key = act_date.isoformat() if hasattr(act_date, 'isoformat') else str(act_date)
        dates[date_key].append({
            "id": act.id,
            "activity_type": act.activity_type,
            "subject": act.subject,
            "description": act.description,
            "scheduled_at": act.scheduled_at.isoformat() if act.scheduled_at else None,
            "due_date": act.due_date.isoformat() if act.due_date else None,
            "is_completed": act.is_completed,
            "priority": act.priority,
            "entity_type": act.entity_type,
            "entity_id": act.entity_id,
        })

    return {
        "start_date": start_date,
        "end_date": end_date,
        "dates": dict(dates),
        "total_activities": len(activities),
    }


@router.get("", response_model=ActivityListResponse)
async def list_activities(
    current_user: CurrentUser,
    db: DBSession,
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    activity_type: Optional[str] = None,
    owner_id: Optional[int] = None,
    assigned_to_id: Optional[int] = None,
    is_completed: Optional[bool] = None,
    priority: Optional[str] = None,
    filters: Optional[str] = None,
):
    """List activities with pagination and filters."""
    import json as _json
    parsed_filters = _json.loads(filters) if filters else None

    if data_scope.can_see_all():
        effective_owner_id = owner_id
    else:
        effective_owner_id = data_scope.owner_id

    service = ActivityService(db)

    activities, total = await service.get_list(
        page=page,
        page_size=page_size,
        entity_type=entity_type,
        entity_id=entity_id,
        activity_type=activity_type,
        owner_id=effective_owner_id,
        assigned_to_id=assigned_to_id,
        is_completed=is_completed,
        priority=priority,
        filters=parsed_filters,
        shared_entity_ids=data_scope.get_shared_ids(ENTITY_TYPE_ACTIVITIES),
    )

    return ActivityListResponse(
        items=[ActivityResponse.model_validate(a) for a in activities],
        total=total,
        page=page,
        page_size=page_size,
        pages=calculate_pages(total, page_size),
    )


@router.post("", response_model=ActivityResponse, status_code=HTTPStatus.CREATED)
async def create_activity(
    activity_data: ActivityCreate,
    request: Request,
    current_user: CurrentUser,
    db: DBSession,
):
    """Create a new activity."""
    service = ActivityService(db)
    activity = await service.create(activity_data, current_user.id)

    ip_address = request.client.host if request.client else None
    await audit_entity_create(db, "activity", activity.id, current_user.id, ip_address)

    await emit(ACTIVITY_CREATED, {
        "entity_id": activity.id,
        "entity_type": "activity",
        "user_id": current_user.id,
        "data": {"activity_type": activity.activity_type, "subject": activity.subject},
    })

    return ActivityResponse.model_validate(activity)


@router.get("/my-tasks", response_model=List[ActivityResponse])
async def get_my_tasks(
    current_user: CurrentUser,
    db: DBSession,
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
    current_user: CurrentUser,
    db: DBSession,
    limit: int = Query(50, ge=1, le=100),
    activity_types: Optional[str] = None,
):
    """Get activity timeline for an entity."""
    timeline = ActivityTimeline(db)

    items = await timeline.get_entity_timeline(
        entity_type=entity_type,
        entity_id=entity_id,
        limit=limit,
        activity_types=parse_comma_separated(activity_types),
    )

    return TimelineResponse(items=[TimelineItem(**item) for item in items])


@router.get("/timeline/user", response_model=TimelineResponse)
async def get_user_timeline(
    current_user: CurrentUser,
    db: DBSession,
    limit: int = Query(50, ge=1, le=100),
    include_assigned: bool = True,
    activity_types: Optional[str] = None,
):
    """Get activity timeline for current user."""
    timeline = ActivityTimeline(db)

    items = await timeline.get_user_timeline(
        user_id=current_user.id,
        limit=limit,
        include_assigned=include_assigned,
        activity_types=parse_comma_separated(activity_types),
    )

    return TimelineResponse(items=[TimelineItem(**item) for item in items])


@router.get("/upcoming", response_model=TimelineResponse)
async def get_upcoming_activities(
    current_user: CurrentUser,
    db: DBSession,
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
    current_user: CurrentUser,
    db: DBSession,
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
    current_user: CurrentUser,
    db: DBSession,
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
):
    """Get an activity by ID."""
    service = ActivityService(db)
    activity = await get_entity_or_404(service, activity_id, EntityNames.ACTIVITY)
    check_record_access_or_shared(
        activity, current_user, data_scope.role_name,
        shared_entity_ids=data_scope.get_shared_ids(ENTITY_TYPE_ACTIVITIES),
    )
    return ActivityResponse.model_validate(activity)


@router.patch("/{activity_id}", response_model=ActivityResponse)
async def update_activity(
    activity_id: int,
    activity_data: ActivityUpdate,
    request: Request,
    current_user: CurrentUser,
    db: DBSession,
):
    """Update an activity."""
    service = ActivityService(db)
    activity = await get_entity_or_404(service, activity_id, EntityNames.ACTIVITY)
    check_ownership(activity, current_user, EntityNames.ACTIVITY)

    update_fields = list(activity_data.model_dump(exclude_unset=True).keys())
    old_data = snapshot_entity(activity, update_fields)

    updated_activity = await service.update(activity, activity_data, current_user.id)

    new_data = snapshot_entity(updated_activity, update_fields)
    ip_address = request.client.host if request.client else None
    await audit_entity_update(db, "activity", updated_activity.id, current_user.id, old_data, new_data, ip_address)

    return ActivityResponse.model_validate(updated_activity)


@router.post("/{activity_id}/complete", response_model=ActivityResponse)
async def complete_activity(
    activity_id: int,
    request: CompleteActivityRequest,
    current_user: CurrentUser,
    db: DBSession,
):
    """Mark an activity as completed."""
    service = ActivityService(db)
    activity = await get_entity_or_404(service, activity_id, EntityNames.ACTIVITY)
    completed_activity = await service.complete(activity, current_user.id, request.notes)
    return ActivityResponse.model_validate(completed_activity)


@router.delete("/{activity_id}", status_code=HTTPStatus.NO_CONTENT)
async def delete_activity(
    activity_id: int,
    request: Request,
    current_user: CurrentUser,
    db: DBSession,
):
    """Delete an activity."""
    service = ActivityService(db)
    activity = await get_entity_or_404(service, activity_id, EntityNames.ACTIVITY)
    check_ownership(activity, current_user, EntityNames.ACTIVITY)

    ip_address = request.client.host if request.client else None
    await audit_entity_delete(db, "activity", activity.id, current_user.id, ip_address)

    await service.delete(activity)
