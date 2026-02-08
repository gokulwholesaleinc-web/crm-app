"""Notification API routes."""

from fastapi import APIRouter, Query

from src.core.router_utils import DBSession, CurrentUser, calculate_pages, raise_not_found
from src.notifications.schemas import (
    NotificationResponse,
    NotificationListResponse,
    UnreadCountResponse,
)
from src.notifications.service import NotificationService

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("", response_model=NotificationListResponse)
async def list_notifications(
    current_user: CurrentUser,
    db: DBSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    unread_only: bool = False,
):
    """List notifications for the current user."""
    service = NotificationService(db)
    items, total = await service.get_list(
        user_id=current_user.id,
        page=page,
        page_size=page_size,
        unread_only=unread_only,
    )
    return NotificationListResponse(
        items=[NotificationResponse.model_validate(n) for n in items],
        total=total,
        page=page,
        page_size=page_size,
        pages=calculate_pages(total, page_size),
    )


@router.get("/unread-count", response_model=UnreadCountResponse)
async def get_unread_count(
    current_user: CurrentUser,
    db: DBSession,
):
    """Get unread notification count."""
    service = NotificationService(db)
    count = await service.get_unread_count(current_user.id)
    return UnreadCountResponse(count=count)


@router.put("/{notification_id}/read", response_model=NotificationResponse)
async def mark_notification_read(
    notification_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Mark a notification as read."""
    service = NotificationService(db)
    notification = await service.mark_read(notification_id, current_user.id)
    if not notification:
        raise_not_found("Notification", notification_id)
    return NotificationResponse.model_validate(notification)


@router.put("/read-all")
async def mark_all_read(
    current_user: CurrentUser,
    db: DBSession,
):
    """Mark all notifications as read."""
    service = NotificationService(db)
    count = await service.mark_all_read(current_user.id)
    return {"updated": count}
