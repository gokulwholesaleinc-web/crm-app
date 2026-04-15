"""Notification service layer."""

import logging
from typing import Optional, List, Tuple

from sqlalchemy import select, func, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.notifications.models import Notification
from src.core.constants import DEFAULT_PAGE_SIZE

logger = logging.getLogger(__name__)


class NotificationService:
    """Service for notification CRUD operations."""

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
        notif = Notification(
            user_id=user_id,
            type=type,
            title=title,
            message=message,
            entity_type=entity_type,
            entity_id=entity_id,
        )
        self.db.add(notif)
        await self.db.flush()
        await self.db.refresh(notif)
        return notif

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
        page_size: int = DEFAULT_PAGE_SIZE,
        unread_only: bool = False,
    ) -> Tuple[List[Notification], int]:
        """Get paginated notifications for a user."""
        filters = [Notification.user_id == user_id]
        if unread_only:
            filters.append(Notification.is_read == False)

        # Count
        count_query = select(func.count()).select_from(
            select(Notification.id).where(*filters).subquery()
        )
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Fetch
        query = (
            select(Notification)
            .where(*filters)
            .order_by(Notification.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self.db.execute(query)
        items = list(result.scalars().all())

        return items, total

    async def mark_read(self, notification_id: int, user_id: int) -> Optional[Notification]:
        """Mark a notification as read."""
        notif = await self.get_by_id(notification_id)
        if not notif or notif.user_id != user_id:
            return None
        notif.is_read = True
        await self.db.flush()
        await self.db.refresh(notif)
        return notif

    async def mark_all_read(self, user_id: int) -> int:
        """Mark all notifications as read for a user. Returns count updated."""
        stmt = (
            update(Notification)
            .where(Notification.user_id == user_id, Notification.is_read == False)
            .values(is_read=True)
        )
        result = await self.db.execute(stmt)
        await self.db.flush()
        return result.rowcount

    async def get_unread_count(self, user_id: int) -> int:
        """Get count of unread notifications for a user."""
        result = await self.db.execute(
            select(func.count()).where(
                Notification.user_id == user_id,
                Notification.is_read == False,
            )
        )
        return result.scalar() or 0

    async def delete_notification(self, notification_id: int, user_id: int) -> bool:
        """Delete a single notification. Returns True if deleted."""
        notif = await self.get_by_id(notification_id)
        if not notif or notif.user_id != user_id:
            return False
        await self.db.delete(notif)
        await self.db.flush()
        return True

    async def delete_all_notifications(self, user_id: int) -> int:
        """Delete all notifications for a user. Returns count deleted."""
        stmt = delete(Notification).where(Notification.user_id == user_id)
        result = await self.db.execute(stmt)
        await self.db.flush()
        return result.rowcount


async def notify_on_assignment(
    db: AsyncSession,
    user_id: int,
    entity_type: str,
    entity_id: int,
    entity_name: str,
) -> Notification:
    """Create a notification when an entity is assigned to a user."""
    service = NotificationService(db)
    return await service.create_notification(
        user_id=user_id,
        type="assignment",
        title=f"{entity_type.rstrip('s').capitalize()} assigned to you",
        message=f"You have been assigned {entity_name}",
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
    """Create a notification when a pipeline stage changes."""
    service = NotificationService(db)
    return await service.create_notification(
        user_id=user_id,
        type="stage_change",
        title=f"Stage changed: {entity_name}",
        message=f"Moved from {old_stage} to {new_stage}",
        entity_type=entity_type,
        entity_id=entity_id,
    )


async def notify_on_mention(
    db: AsyncSession,
    mentioned_user_id: int,
    author_name: str,
    entity_type: str,
    entity_id: int,
    content_snippet: str,
) -> Notification:
    """Create a notification when a user is @mentioned."""
    service = NotificationService(db)
    return await service.create_notification(
        user_id=mentioned_user_id,
        type="mention",
        title=f"{author_name} mentioned you",
        message=content_snippet[:200],
        entity_type=entity_type,
        entity_id=entity_id,
    )


async def notify_on_activity_due(
    db: AsyncSession,
    user_id: int,
    activity_id: int,
    activity_subject: str,
) -> Notification:
    """Create a notification when an activity is due."""
    service = NotificationService(db)
    return await service.create_notification(
        user_id=user_id,
        type="activity_due",
        title="Activity due",
        message=f'Activity "{activity_subject}" is due soon',
        entity_type="activities",
        entity_id=activity_id,
    )


async def notify_admins_of_pending_user(db: AsyncSession, user: User) -> None:
    """Notify every active admin that a new user is awaiting approval.

    Best-effort: a failure to create a single notification is logged and
    swallowed so it can't abort the sign-up transaction (which would
    silently rollback the newly-created user row and leave the requester
    stuck in a retry loop).
    """
    result = await db.execute(
        select(User).where(
            (User.is_superuser == True) | (User.role == "admin"),
            User.is_active == True,
        )
    )
    admins = result.scalars().all()
    service = NotificationService(db)
    for admin in admins:
        try:
            await service.create_notification(
                user_id=admin.id,
                type="pending_approval",
                title="New access request",
                message=f"New access request: {user.full_name} ({user.email})",
                entity_type="users",
                entity_id=user.id,
            )
        except Exception:
            logger.exception(
                "Failed to notify admin %s of pending user %s",
                admin.id,
                user.id,
            )
