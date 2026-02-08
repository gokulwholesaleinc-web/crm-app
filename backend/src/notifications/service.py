"""Notification service for creating and managing notifications."""

from typing import Optional, Tuple, List

from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.notifications.models import Notification


class NotificationService:
    """Service for notification management."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_notification(
        self,
        user_id: int,
        type: str,
        title: str,
        message: str,
        entity_type: Optional[str] = None,
        entity_id: Optional[int] = None,
    ) -> Notification:
        """Create a new notification."""
        notification = Notification(
            user_id=user_id,
            type=type,
            title=title,
            message=message,
            entity_type=entity_type,
            entity_id=entity_id,
        )
        self.db.add(notification)
        await self.db.flush()
        return notification

    async def get_by_id(self, notification_id: int) -> Optional[Notification]:
        """Get a notification by ID."""
        result = await self.db.execute(
            select(Notification).where(Notification.id == notification_id)
        )
        return result.scalar_one_or_none()

    async def get_list(
        self,
        user_id: int,
        page: int = 1,
        page_size: int = 20,
        unread_only: bool = False,
    ) -> Tuple[List[Notification], int]:
        """Get paginated notifications for a user."""
        query = select(Notification).where(Notification.user_id == user_id)
        count_query = select(func.count()).select_from(Notification).where(
            Notification.user_id == user_id
        )

        if unread_only:
            query = query.where(Notification.is_read == False)
            count_query = count_query.where(Notification.is_read == False)

        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        offset = (page - 1) * page_size
        query = query.order_by(Notification.created_at.desc()).offset(offset).limit(page_size)
        result = await self.db.execute(query)
        items = list(result.scalars().all())

        return items, total

    async def mark_read(self, notification_id: int, user_id: int) -> Optional[Notification]:
        """Mark a single notification as read."""
        notification = await self.get_by_id(notification_id)
        if notification and notification.user_id == user_id:
            notification.is_read = True
        return notification

    async def mark_all_read(self, user_id: int) -> int:
        """Mark all notifications as read for a user. Returns count updated."""
        result = await self.db.execute(
            update(Notification)
            .where(Notification.user_id == user_id, Notification.is_read == False)
            .values(is_read=True)
        )
        return result.rowcount

    async def get_unread_count(self, user_id: int) -> int:
        """Get unread notification count for a user."""
        result = await self.db.execute(
            select(func.count())
            .select_from(Notification)
            .where(Notification.user_id == user_id, Notification.is_read == False)
        )
        return result.scalar() or 0


async def notify_on_assignment(
    db: AsyncSession,
    assigned_to_id: int,
    assigner_name: str,
    entity_type: str,
    entity_id: int,
    entity_name: str,
) -> Notification:
    """Create notification when an entity is assigned to a user."""
    service = NotificationService(db)
    return await service.create_notification(
        user_id=assigned_to_id,
        type="assignment",
        title=f"New {entity_type} assigned",
        message=f"{assigner_name} assigned you {entity_type} '{entity_name}'",
        entity_type=entity_type,
        entity_id=entity_id,
    )


async def notify_on_stage_change(
    db: AsyncSession,
    user_id: int,
    entity_type: str,
    entity_id: int,
    entity_name: str,
    old_stage: str,
    new_stage: str,
) -> Notification:
    """Create notification when a pipeline stage changes."""
    service = NotificationService(db)
    return await service.create_notification(
        user_id=user_id,
        type="stage_change",
        title=f"{entity_type.title()} stage updated",
        message=f"'{entity_name}' moved from {old_stage} to {new_stage}",
        entity_type=entity_type,
        entity_id=entity_id,
    )


async def notify_on_activity_due(
    db: AsyncSession,
    user_id: int,
    activity_subject: str,
    activity_id: int,
) -> Notification:
    """Create notification when an activity is due."""
    service = NotificationService(db)
    return await service.create_notification(
        user_id=user_id,
        type="activity_due",
        title="Activity due",
        message=f"Activity '{activity_subject}' is due",
        entity_type="activities",
        entity_id=activity_id,
    )
