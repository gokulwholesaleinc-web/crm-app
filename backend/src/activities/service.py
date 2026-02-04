"""Activity service layer."""

from datetime import datetime, timezone
from typing import Optional, List, Tuple
from sqlalchemy import select, func, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession
from src.activities.models import Activity
from src.activities.schemas import ActivityCreate, ActivityUpdate


class ActivityService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, activity_id: int) -> Optional[Activity]:
        """Get activity by ID."""
        result = await self.db.execute(
            select(Activity).where(Activity.id == activity_id)
        )
        return result.scalar_one_or_none()

    async def get_list(
        self,
        page: int = 1,
        page_size: int = 20,
        entity_type: Optional[str] = None,
        entity_id: Optional[int] = None,
        activity_type: Optional[str] = None,
        owner_id: Optional[int] = None,
        assigned_to_id: Optional[int] = None,
        is_completed: Optional[bool] = None,
        priority: Optional[str] = None,
    ) -> Tuple[List[Activity], int]:
        """Get paginated list of activities with filters."""
        query = select(Activity)

        if entity_type:
            query = query.where(Activity.entity_type == entity_type)

        if entity_id:
            query = query.where(Activity.entity_id == entity_id)

        if activity_type:
            query = query.where(Activity.activity_type == activity_type)

        if owner_id:
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
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(activity, field, value)
        activity.updated_by_id = user_id
        await self.db.flush()
        await self.db.refresh(activity)
        return activity

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

    async def delete(self, activity: Activity) -> None:
        """Delete an activity."""
        await self.db.delete(activity)
        await self.db.flush()

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
            .where(Activity.activity_type == "task")
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
