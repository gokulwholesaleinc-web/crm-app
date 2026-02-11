"""Activity service layer."""

from datetime import datetime, timezone
from typing import Optional, List, Tuple, Any, Dict
from sqlalchemy import select, func, or_
from src.activities.models import Activity, ActivityType
from src.core.filtering import apply_filters_to_query
from src.activities.schemas import ActivityCreate, ActivityUpdate
from src.core.base_service import CRUDService
from src.core.constants import DEFAULT_PAGE_SIZE


class ActivityService(CRUDService[Activity, ActivityCreate, ActivityUpdate]):
    """Service for Activity CRUD operations."""

    model = Activity
    # Activities don't have tag_ids in their schemas
    create_exclude_fields: set = set()
    update_exclude_fields: set = set()

    async def get_list(
        self,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
        entity_type: Optional[str] = None,
        entity_id: Optional[int] = None,
        activity_type: Optional[str] = None,
        owner_id: Optional[int] = None,
        assigned_to_id: Optional[int] = None,
        is_completed: Optional[bool] = None,
        priority: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        shared_entity_ids: Optional[List[int]] = None,
    ) -> Tuple[List[Activity], int]:
        """Get paginated list of activities with filters."""
        query = select(Activity)

        if filters:
            query = apply_filters_to_query(query, Activity, filters)

        if entity_type:
            query = query.where(Activity.entity_type == entity_type)

        if entity_id:
            query = query.where(Activity.entity_id == entity_id)

        if activity_type:
            query = query.where(Activity.activity_type == activity_type)

        if owner_id:
            if shared_entity_ids:
                query = query.where(or_(Activity.owner_id == owner_id, Activity.id.in_(shared_entity_ids)))
            else:
                query = query.where(Activity.owner_id == owner_id)

        if assigned_to_id:
            query = query.where(Activity.assigned_to_id == assigned_to_id)

        if is_completed is not None:
            query = query.where(Activity.is_completed == is_completed)

        if priority:
            query = query.where(Activity.priority == priority)

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar()

        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(Activity.created_at.desc())

        result = await self.db.execute(query)
        activities = list(result.scalars().all())

        return activities, total

    async def create(self, data: ActivityCreate, user_id: int) -> Activity:
        """Create a new activity."""
        activity_data = data.model_dump()
        if not activity_data.get("owner_id"):
            activity_data["owner_id"] = user_id

        activity = Activity(**activity_data, created_by_id=user_id)
        self.db.add(activity)
        await self.db.flush()
        await self.db.refresh(activity)
        return activity

    async def update(self, activity: Activity, data: ActivityUpdate, user_id: int) -> Activity:
        """Update an activity."""
        return await super().update(activity, data, user_id)

    async def complete(self, activity: Activity, user_id: int, notes: Optional[str] = None) -> Activity:
        """Mark an activity as completed."""
        activity.is_completed = True
        activity.completed_at = datetime.now(timezone.utc)
        if notes:
            if activity.description:
                activity.description += f"\n\n---\nCompletion notes: {notes}"
            else:
                activity.description = f"Completion notes: {notes}"
        activity.updated_by_id = user_id
        await self.db.flush()
        await self.db.refresh(activity)
        return activity

    async def get_entity_activities(
        self,
        entity_type: str,
        entity_id: int,
        limit: int = 50,
    ) -> List[Activity]:
        """Get all activities for a specific entity."""
        result = await self.db.execute(
            select(Activity)
            .where(Activity.entity_type == entity_type)
            .where(Activity.entity_id == entity_id)
            .order_by(Activity.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_my_tasks(
        self,
        user_id: int,
        include_completed: bool = False,
        limit: int = 50,
    ) -> List[Activity]:
        """Get tasks assigned to or owned by user."""
        query = (
            select(Activity)
            .where(Activity.activity_type == ActivityType.TASK.value)
            .where(
                or_(
                    Activity.owner_id == user_id,
                    Activity.assigned_to_id == user_id,
                )
            )
        )

        if not include_completed:
            query = query.where(Activity.is_completed == False)

        query = query.order_by(
            Activity.due_date.asc().nullslast(),
            Activity.priority.desc(),
        ).limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())
