"""Google Calendar integration API routes."""

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
    auth_url = service.get_authorization_url(redirect_uri, state=str(current_user.id))
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
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=f"Sync failed: {str(exc)}")
    return {"synced": len(created), "events": created}


@router.post("/push")
async def push_to_calendar(
    data: GoogleCalendarEventCreate,
    current_user: CurrentUser,
    db: DBSession,
):
    """Push a CRM activity to Google Calendar."""
    service = GoogleCalendarService(db)
    try:
        sync_event = await service.create_calendar_event(current_user.id, data.activity_id)
    except Exception as exc:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=f"Push failed: {str(exc)}")
    if not sync_event:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="Calendar not connected or activity not found")
    return {"google_event_id": sync_event.google_event_id, "activity_id": sync_event.activity_id}
