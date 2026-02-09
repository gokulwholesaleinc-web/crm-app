"""Notification API routes."""

from typing import Optional
from fastapi import APIRouter, Query, HTTPException
from src.core.constants import HTTPStatus
from src.core.router_utils import DBSession, CurrentUser, calculate_pages
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
    unread_only: bool = Query(False),
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
    """Get the count of unread notifications."""
    service = NotificationService(db)
    count = await service.get_unread_count(current_user.id)
    return UnreadCountResponse(count=count)


@router.put("/{notification_id}/read", response_model=NotificationResponse)
async def mark_read(
    notification_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Mark a notification as read."""
    service = NotificationService(db)
    notif = await service.mark_read(notification_id, current_user.id)
    if not notif:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail=f"Notification with ID {notification_id} not found",
        )
    return notif


@router.put("/read-all")
async def mark_all_read(
    current_user: CurrentUser,
    db: DBSession,
):
    """Mark all notifications as read for the current user."""
    service = NotificationService(db)
    updated = await service.mark_all_read(current_user.id)
    return {"updated": updated}
