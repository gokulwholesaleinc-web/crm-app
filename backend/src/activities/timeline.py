"""Activity timeline utilities."""

from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy import select, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession
from src.activities.models import Activity


class ActivityTimeline:
    """Generates unified activity timeline for entities."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_entity_timeline(
        self,
        entity_type: str,
        entity_id: int,
        limit: int = 50,
        activity_types: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get activity timeline for a specific entity.

        Returns activities sorted by date (most recent first).
        """
        query = (
            select(Activity)
            .where(Activity.entity_type == entity_type)
            .where(Activity.entity_id == entity_id)
        )

        if activity_types:
            query = query.where(Activity.activity_type.in_(activity_types))

        query = query.order_by(Activity.created_at.desc()).limit(limit)

        result = await self.db.execute(query)
        activities = result.scalars().all()

        return [self._format_activity(a) for a in activities]

    async def get_user_timeline(
        self,
        user_id: int,
        limit: int = 50,
        include_assigned: bool = True,
        activity_types: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get activity timeline for a user (owned or assigned activities).
        """
        conditions = [Activity.owner_id == user_id]
        if include_assigned:
            conditions.append(Activity.assigned_to_id == user_id)

        query = select(Activity).where(or_(*conditions))

        if activity_types:
            query = query.where(Activity.activity_type.in_(activity_types))

        query = query.order_by(Activity.created_at.desc()).limit(limit)

        result = await self.db.execute(query)
        activities = result.scalars().all()

        return [self._format_activity(a) for a in activities]

    async def get_upcoming_activities(
        self,
        user_id: int,
        days_ahead: int = 7,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Get upcoming scheduled activities for a user.
        """
        now = datetime.now()
        future = now + timedelta(days=days_ahead)

        query = (
            select(Activity)
            .where(
                or_(
                    Activity.owner_id == user_id,
                    Activity.assigned_to_id == user_id,
                )
            )
            .where(Activity.is_completed == False)
            .where(
                or_(
                    and_(
                        Activity.scheduled_at != None,
                        Activity.scheduled_at >= now,
                        Activity.scheduled_at <= future,
                    ),
                    and_(
                        Activity.due_date != None,
                        Activity.due_date >= now.date(),
                        Activity.due_date <= future.date(),
                    ),
                )
            )
            .order_by(Activity.scheduled_at.asc().nullslast(), Activity.due_date.asc().nullslast())
            .limit(limit)
        )

        result = await self.db.execute(query)
        activities = result.scalars().all()

        return [self._format_activity(a) for a in activities]

    async def get_overdue_tasks(
        self,
        user_id: int,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Get overdue tasks for a user.
        """
        today = datetime.now().date()

        query = (
            select(Activity)
            .where(
                or_(
                    Activity.owner_id == user_id,
                    Activity.assigned_to_id == user_id,
                )
            )
            .where(Activity.is_completed == False)
            .where(Activity.due_date < today)
            .order_by(Activity.due_date.asc())
            .limit(limit)
        )

        result = await self.db.execute(query)
        activities = result.scalars().all()

        return [self._format_activity(a) for a in activities]

    def _format_activity(self, activity: Activity) -> Dict[str, Any]:
        """Format activity for timeline display."""
        return {
            "id": activity.id,
            "activity_type": activity.activity_type,
            "subject": activity.subject,
            "description": activity.description,
            "entity_type": activity.entity_type,
            "entity_id": activity.entity_id,
            "scheduled_at": activity.scheduled_at.isoformat() if activity.scheduled_at else None,
            "due_date": activity.due_date.isoformat() if activity.due_date else None,
            "completed_at": activity.completed_at.isoformat() if activity.completed_at else None,
            "is_completed": activity.is_completed,
            "priority": activity.priority,
            "created_at": activity.created_at.isoformat(),
            "owner_id": activity.owner_id,
            "assigned_to_id": activity.assigned_to_id,
            # Type-specific fields
            "call_duration_minutes": activity.call_duration_minutes,
            "call_outcome": activity.call_outcome,
            "meeting_location": activity.meeting_location,
        }
