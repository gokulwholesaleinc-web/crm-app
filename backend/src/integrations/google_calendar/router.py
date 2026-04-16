"""Google Calendar integration API routes."""

import logging

from fastapi import APIRouter, HTTPException
from src.core.router_utils import DBSession, CurrentUser
from src.core.constants import HTTPStatus
from src.integrations.google_calendar.service import GoogleCalendarService
from src.integrations.google_calendar.schemas import (
    GoogleCalendarConnect,
    GoogleCalendarCallback,
    GoogleCalendarCredentialResponse,
    GoogleCalendarEventCreate,
    CalendarSyncStatus,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/integrations/google-calendar", tags=["google-calendar"])


@router.get("/status", response_model=CalendarSyncStatus)
async def get_sync_status(
    current_user: CurrentUser,
    db: DBSession,
):
    """Get the current user's Google Calendar connection status."""
    service = GoogleCalendarService(db)
    status = await service.get_sync_status(current_user.id)
    return CalendarSyncStatus(**status)


@router.post("/connect")
async def get_auth_url(
    data: GoogleCalendarConnect,
    current_user: CurrentUser,
    db: DBSession,
):
    """Get the Google OAuth2 authorization URL to start the connection flow."""
    from src.config import settings
    client_id = getattr(settings, "GOOGLE_CLIENT_ID", "")
    if not client_id:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="Google Calendar integration is not configured")

    service = GoogleCalendarService(db)
    redirect_uri = data.redirect_uri or ""
    auth_url = service.get_authorization_url(redirect_uri, state=str(current_user.id), login_hint=current_user.email)
    return {"auth_url": auth_url}


@router.post("/callback", response_model=GoogleCalendarCredentialResponse)
async def handle_callback(
    data: GoogleCalendarCallback,
    current_user: CurrentUser,
    db: DBSession,
):
    """Handle the OAuth2 callback and store credentials."""
    service = GoogleCalendarService(db)
    redirect_uri = data.redirect_uri or ""
    if not redirect_uri:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="redirect_uri is required and must match the one used in /connect",
        )
    try:
        credential = await service.exchange_code(data.code, redirect_uri, current_user.id)
    except Exception as exc:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=f"Failed to connect: {str(exc)}")
    return GoogleCalendarCredentialResponse.model_validate(credential)


@router.delete("/disconnect", status_code=HTTPStatus.NO_CONTENT)
async def disconnect(
    current_user: CurrentUser,
    db: DBSession,
):
    """Disconnect Google Calendar integration."""
    service = GoogleCalendarService(db)
    removed = await service.disconnect(current_user.id)
    if not removed:
        raise HTTPException(status_code=404, detail="No Google Calendar connection found")


@router.post("/sync")
async def sync_calendar(
    current_user: CurrentUser,
    db: DBSession,
):
    """Pull events from Google Calendar into CRM activities."""
    service = GoogleCalendarService(db)
    try:
        created = await service.sync_from_google(current_user.id)
    except Exception as exc:
        response_text = getattr(getattr(exc, "response", None), "text", None)
        logger.exception(
            "Calendar sync failed for user_id=%s: %s(%s)%s",
            current_user.id,
            type(exc).__name__,
            exc,
            f" | response: {response_text}" if response_text else "",
        )
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=f"Sync failed: {str(exc)}")
    return {"synced": len(created), "events": created}


@router.post("/push")
async def push_to_calendar(
    data: GoogleCalendarEventCreate,
    current_user: CurrentUser,
    db: DBSession,
):
    """Push a CRM activity to Google Calendar.

    Verifies the caller owns the activity (or is admin/manager) before
    calling Google so you can't push another user's private activity
    into your own calendar.
    """
    from sqlalchemy import select
    from src.activities.models import Activity
    from src.core.router_utils import raise_forbidden

    activity_result = await db.execute(
        select(Activity).where(Activity.id == data.activity_id)
    )
    activity = activity_result.scalar_one_or_none()
    if activity is None:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Activity not found"
        )
    is_privileged = current_user.is_superuser or getattr(current_user, "role", "sales_rep") in ("admin", "manager")
    if not is_privileged:
        owns = (
            activity.owner_id == current_user.id
            or activity.assigned_to_id == current_user.id
            or activity.created_by_id == current_user.id
        )
        if not owns:
            raise_forbidden("You do not have permission to push this activity")

    service = GoogleCalendarService(db)
    try:
        sync_event = await service.create_calendar_event(current_user.id, data.activity_id)
    except Exception as exc:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=f"Push failed: {str(exc)}")
    if not sync_event:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="Calendar not connected or activity not found")
    return {"google_event_id": sync_event.google_event_id, "activity_id": sync_event.activity_id}
