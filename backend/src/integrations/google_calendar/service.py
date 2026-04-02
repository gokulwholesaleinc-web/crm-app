"""Google Calendar integration service.

Handles OAuth2 flow, event creation, and two-way sync between
CRM activities and Google Calendar events.

Requires GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in env.
"""

import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from urllib.parse import urlencode

import httpx
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.integrations.google_calendar.models import GoogleCalendarCredential, CalendarSyncEvent
from src.activities.models import Activity

logger = logging.getLogger(__name__)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_CALENDAR_API = "https://www.googleapis.com/calendar/v3"
SCOPES = "https://www.googleapis.com/auth/calendar"


class GoogleCalendarService:
    """Service for Google Calendar OAuth and event sync."""

    def __init__(self, db: AsyncSession):
        self.db = db

    def get_authorization_url(self, redirect_uri: str, state: Optional[str] = None) -> str:
        """Build the Google OAuth2 authorization URL."""
        params = {
            "client_id": getattr(settings, "GOOGLE_CLIENT_ID", ""),
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": SCOPES,
            "access_type": "offline",
            "prompt": "consent",
        }
        if state:
            params["state"] = state
        return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str, redirect_uri: str, user_id: int) -> GoogleCalendarCredential:
        """Exchange authorization code for access/refresh tokens and store credentials."""
        client_id = getattr(settings, "GOOGLE_CLIENT_ID", "")
        client_secret = getattr(settings, "GOOGLE_CLIENT_SECRET", "")

        async with httpx.AsyncClient() as client:
            response = await client.post(GOOGLE_TOKEN_URL, data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            })
            response.raise_for_status()
            token_data = response.json()

        return await self._upsert_credential(user_id, token_data)

    async def refresh_access_token(self, credential: GoogleCalendarCredential) -> GoogleCalendarCredential:
        """Refresh an expired access token using the refresh token."""
        if not credential.refresh_token:
            raise ValueError("No refresh token available — user must re-authorize")

        client_id = getattr(settings, "GOOGLE_CLIENT_ID", "")
        client_secret = getattr(settings, "GOOGLE_CLIENT_SECRET", "")

        async with httpx.AsyncClient() as client:
            response = await client.post(GOOGLE_TOKEN_URL, data={
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": credential.refresh_token,
                "grant_type": "refresh_token",
            })
            response.raise_for_status()
            token_data = response.json()

        credential.access_token = token_data["access_token"]
        if "refresh_token" in token_data:
            credential.refresh_token = token_data["refresh_token"]
        if "expires_in" in token_data:
            from datetime import timedelta
            credential.token_expiry = datetime.now(timezone.utc) + timedelta(seconds=token_data["expires_in"])
        await self.db.flush()
        return credential

    async def get_credential(self, user_id: int) -> Optional[GoogleCalendarCredential]:
        """Get the stored Google Calendar credential for a user."""
        result = await self.db.execute(
            select(GoogleCalendarCredential).where(
                GoogleCalendarCredential.user_id == user_id
            )
        )
        return result.scalar_one_or_none()

    async def disconnect(self, user_id: int) -> bool:
        """Remove Google Calendar connection for a user."""
        credential = await self.get_credential(user_id)
        if not credential:
            return False
        await self.db.delete(credential)
        await self.db.flush()
        return True

    async def get_sync_status(self, user_id: int) -> Dict[str, Any]:
        """Get the sync status for a user."""
        credential = await self.get_credential(user_id)
        count_result = await self.db.execute(
            select(func.count()).select_from(
                select(CalendarSyncEvent).where(CalendarSyncEvent.user_id == user_id).subquery()
            )
        )
        synced_count = count_result.scalar() or 0

        return {
            "connected": credential is not None and credential.is_active,
            "calendar_id": credential.calendar_id if credential else None,
            "last_synced_at": credential.last_synced_at if credential else None,
            "synced_events_count": synced_count,
        }

    async def _get_valid_token(self, credential: GoogleCalendarCredential) -> str:
        """Get a valid access token, refreshing if expired."""
        if credential.token_expiry and credential.token_expiry <= datetime.now(timezone.utc):
            credential = await self.refresh_access_token(credential)
        return credential.access_token

    async def create_calendar_event(
        self,
        user_id: int,
        activity_id: int,
    ) -> Optional[CalendarSyncEvent]:
        """Create a Google Calendar event from a CRM activity."""
        credential = await self.get_credential(user_id)
        if not credential or not credential.is_active:
            return None

        result = await self.db.execute(
            select(Activity).where(Activity.id == activity_id)
        )
        activity = result.scalar_one_or_none()
        if not activity:
            return None

        token = await self._get_valid_token(credential)
        event_body = self._activity_to_event(activity)

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{GOOGLE_CALENDAR_API}/calendars/{credential.calendar_id}/events",
                json=event_body,
                headers={"Authorization": f"Bearer {token}"},
            )
            response.raise_for_status()
            event_data = response.json()

        sync_event = CalendarSyncEvent(
            user_id=user_id,
            activity_id=activity_id,
            google_event_id=event_data["id"],
            google_calendar_id=credential.calendar_id,
            sync_direction="crm_to_google",
        )
        self.db.add(sync_event)
        await self.db.flush()
        return sync_event

    async def sync_from_google(self, user_id: int) -> List[Dict[str, Any]]:
        """Pull events from Google Calendar and create CRM activities.

        Returns a list of created activity summaries.
        """
        credential = await self.get_credential(user_id)
        if not credential or not credential.is_active:
            return []

        token = await self._get_valid_token(credential)

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{GOOGLE_CALENDAR_API}/calendars/{credential.calendar_id}/events",
                params={
                    "maxResults": 50,
                    "orderBy": "updated",
                    "singleEvents": True,
                    "timeMin": datetime.now(timezone.utc).isoformat(),
                },
                headers={"Authorization": f"Bearer {token}"},
            )
            response.raise_for_status()
            events_data = response.json()

        created = []
        for event in events_data.get("items", []):
            existing = await self.db.execute(
                select(CalendarSyncEvent).where(
                    CalendarSyncEvent.user_id == user_id,
                    CalendarSyncEvent.google_event_id == event["id"],
                )
            )
            if existing.scalar_one_or_none():
                continue

            activity = self._event_to_activity(event, user_id)
            self.db.add(activity)
            await self.db.flush()

            sync_event = CalendarSyncEvent(
                user_id=user_id,
                activity_id=activity.id,
                google_event_id=event["id"],
                google_calendar_id=credential.calendar_id,
                sync_direction="google_to_crm",
            )
            self.db.add(sync_event)
            created.append({"activity_id": activity.id, "google_event_id": event["id"], "summary": event.get("summary")})

        credential.last_synced_at = datetime.now(timezone.utc)
        await self.db.flush()
        return created

    async def _upsert_credential(self, user_id: int, token_data: dict) -> GoogleCalendarCredential:
        """Create or update Google Calendar credentials for a user."""
        from datetime import timedelta

        existing = await self.get_credential(user_id)
        expiry = None
        if "expires_in" in token_data:
            expiry = datetime.now(timezone.utc) + timedelta(seconds=token_data["expires_in"])

        if existing:
            existing.access_token = token_data["access_token"]
            if "refresh_token" in token_data:
                existing.refresh_token = token_data["refresh_token"]
            existing.token_expiry = expiry
            existing.is_active = True
            await self.db.flush()
            return existing

        credential = GoogleCalendarCredential(
            user_id=user_id,
            access_token=token_data["access_token"],
            refresh_token=token_data.get("refresh_token"),
            token_expiry=expiry,
        )
        self.db.add(credential)
        await self.db.flush()
        return credential

    def _activity_to_event(self, activity: Activity) -> dict:
        """Convert a CRM activity to a Google Calendar event payload."""
        event = {
            "summary": activity.subject or "CRM Activity",
            "description": activity.description or "",
        }
        if activity.due_date:
            event["start"] = {"date": str(activity.due_date)}
            event["end"] = {"date": str(activity.due_date)}
        else:
            now = datetime.now(timezone.utc).isoformat()
            event["start"] = {"dateTime": now}
            event["end"] = {"dateTime": now}
        return event

    def _event_to_activity(self, event: dict, user_id: int) -> Activity:
        """Convert a Google Calendar event to a CRM activity."""
        due_date = None
        start = event.get("start", {})
        if "date" in start:
            due_date = datetime.strptime(start["date"], "%Y-%m-%d").date()
        elif "dateTime" in start:
            due_date = datetime.fromisoformat(start["dateTime"].replace("Z", "+00:00")).date()

        return Activity(
            activity_type="meeting",
            subject=event.get("summary", "Google Calendar Event"),
            description=event.get("description", ""),
            due_date=due_date,
            is_completed=False,
            priority="normal",
            owner_id=user_id,
            assigned_to_id=user_id,
        )
