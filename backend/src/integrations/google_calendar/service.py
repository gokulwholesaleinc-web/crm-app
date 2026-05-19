"""Google Calendar integration service.

Handles OAuth2 flow, event creation, and two-way sync between
CRM activities and Google Calendar events.

Requires GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in env.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.activities.models import Activity
from src.config import settings
from src.core.constants import ENTITY_TYPE_USERS
from src.integrations.google_calendar.models import CalendarSyncEvent, GoogleCalendarCredential

logger = logging.getLogger(__name__)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_CALENDAR_API = "https://www.googleapis.com/calendar/v3"
SCOPES = "https://www.googleapis.com/auth/calendar"

GOOGLE_CALENDAR_PAGE_SIZE = 2500
CALENDAR_SYNC_HORIZON_DAYS = 90
CALENDAR_SYNC_LOCK_NAMESPACE = 100_001

# Discriminator stored on the credential row so /status can distinguish
# `needs_reconnect` (Google revoked us) from `disconnected` (user clicked
# Disconnect or never connected). Mirrors the Gmail `GmailAuthError:`
# convention. We don't add a column for it — when refresh fails with
# invalid_grant we set is_active=False AND blank the tokens, which the
# status endpoint reads as `needs_reconnect`.


class CalendarReauthRequiredError(Exception):
    """Google rejected our OAuth2 token; user must re-authorize.

    The 400 response from oauth2.googleapis.com/token with
    `error=invalid_grant` happens when:
      - The user revoked our app's access in Google Account settings.
      - The refresh token expired (e.g., 6 months unused, app in test
        mode with 7-day refresh tokens).
      - Google rotated the refresh token and our stored one is stale.

    In all three cases the only fix is the user re-running the OAuth
    flow. Bubbling this as a typed error lets the router surface a
    clear "Reconnect required" message instead of a generic 400.
    """


class GoogleCalendarService:
    """Service for Google Calendar OAuth and event sync."""

    def __init__(self, db: AsyncSession):
        self.db = db

    def get_authorization_url(self, redirect_uri: str, state: str | None = None, login_hint: str | None = None) -> str:
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
        if login_hint:
            params["login_hint"] = login_hint
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
            # No refresh token on file ≡ Google won't give us a new
            # access token; the user has to re-OAuth. Flip is_active so
            # /status reports `needs_reconnect` (a row exists but is
            # inactive — distinct from "disconnected" where no row).
            credential.is_active = False
            await self.db.flush()
            raise CalendarReauthRequiredError(
                "No refresh token on file — please reconnect Google Calendar."
            )

        client_id = getattr(settings, "GOOGLE_CLIENT_ID", "")
        client_secret = getattr(settings, "GOOGLE_CLIENT_SECRET", "")

        async with httpx.AsyncClient() as client:
            response = await client.post(GOOGLE_TOKEN_URL, data={
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": credential.refresh_token,
                "grant_type": "refresh_token",
            })

        # Google returns 400 with `{"error": "invalid_grant"}` when our
        # refresh token has been revoked, expired, or rotated. 401 is
        # used for some auth misconfigurations. Either way the only fix
        # is for the user to re-OAuth, so we mark the credential
        # inactive (preserving the row so /status can report
        # needs_reconnect) and surface a typed error to the router.
        if response.status_code in (400, 401):
            try:
                error_code = response.json().get("error", "") or ""
            except ValueError:
                error_code = ""
            credential.is_active = False
            credential.access_token = ""
            await self.db.flush()
            logger.warning(
                "Google Calendar refresh rejected for user_id=%s "
                "(status=%s, error=%s) — credential marked needs_reconnect",
                credential.user_id,
                response.status_code,
                error_code,
            )
            raise CalendarReauthRequiredError(
                f"Google rejected our refresh token ({error_code or response.status_code}). "
                "Please reconnect Google Calendar."
            )
        response.raise_for_status()
        token_data = response.json()

        credential.access_token = token_data["access_token"]
        if "refresh_token" in token_data:
            credential.refresh_token = token_data["refresh_token"]
        if "expires_in" in token_data:
            credential.token_expiry = datetime.now(UTC) + timedelta(seconds=token_data["expires_in"])
        await self.db.flush()
        return credential

    async def get_credential(self, user_id: int) -> GoogleCalendarCredential | None:
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

    async def get_sync_status(self, user_id: int) -> dict[str, Any]:
        credential = await self.get_credential(user_id)
        count_result = await self.db.execute(
            select(func.count()).select_from(
                select(CalendarSyncEvent).where(CalendarSyncEvent.user_id == user_id).subquery()
            )
        )
        synced_count = count_result.scalar() or 0

        # State derivation matches the Gmail pattern. The row's presence
        # vs. its is_active flag is the discriminator: refresh_access_token
        # flips is_active=False (without deleting the row) when Google
        # rejects our refresh token, so we can tell needs_reconnect apart
        # from a clean manual disconnect (which deletes the row outright).
        if credential is None:
            state = "disconnected"
            last_error = None
        elif credential.is_active:
            state = "connected"
            last_error = None
        else:
            state = "needs_reconnect"
            last_error = (
                "Google rejected our refresh token. Reconnect to resume sync."
            )

        return {
            "state": state,
            "connected": credential is not None and credential.is_active,
            "calendar_id": credential.calendar_id if credential else None,
            "last_synced_at": credential.last_synced_at if credential else None,
            "synced_events_count": synced_count,
            "last_error": last_error,
        }

    async def _get_valid_token(self, credential: GoogleCalendarCredential) -> str:
        """Get a valid access token, refreshing if expired."""
        if credential.token_expiry and credential.token_expiry <= datetime.now(UTC):
            credential = await self.refresh_access_token(credential)
        return credential.access_token

    async def create_calendar_event(
        self,
        user_id: int,
        activity_id: int,
    ) -> CalendarSyncEvent | None:
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

    async def sync_from_google(self, user_id: int) -> list[dict[str, Any]]:
        """Pull upcoming events from Google Calendar into CRM activities."""
        has_lock = False
        try:
            locked = await self.db.execute(
                text("SELECT pg_try_advisory_lock(:ns, :uid)"),
                {"ns": CALENDAR_SYNC_LOCK_NAMESPACE, "uid": user_id},
            )
            if not locked.scalar():
                logger.info("Calendar sync already running for user_id=%s, skipping", user_id)
                return []
            has_lock = True
        except Exception:
            logger.debug("Advisory lock unavailable (non-PostgreSQL?), proceeding without lock")

        try:
            return await self._sync_from_google_locked(user_id)
        finally:
            if has_lock:
                await self.db.execute(
                    text("SELECT pg_advisory_unlock(:ns, :uid)"),
                    {"ns": CALENDAR_SYNC_LOCK_NAMESPACE, "uid": user_id},
                )

    async def _sync_from_google_locked(self, user_id: int) -> list[dict[str, Any]]:
        credential = await self.get_credential(user_id)
        if not credential or not credential.is_active:
            return []

        token = await self._get_valid_token(credential)
        now = datetime.now(UTC)
        time_min_iso = now.isoformat()
        time_max_iso = (now + timedelta(days=CALENDAR_SYNC_HORIZON_DAYS)).isoformat()

        created = []
        page_token: str | None = None

        async with httpx.AsyncClient() as client:
            while True:
                params = {
                    "maxResults": GOOGLE_CALENDAR_PAGE_SIZE,
                    "orderBy": "updated",
                    "singleEvents": True,
                    "timeMin": time_min_iso,
                    "timeMax": time_max_iso,
                }
                if page_token:
                    params["pageToken"] = page_token

                response = await client.get(
                    f"{GOOGLE_CALENDAR_API}/calendars/{credential.calendar_id}/events",
                    params=params,
                    headers={"Authorization": f"Bearer {token}"},
                )
                response.raise_for_status()
                events_data = response.json()

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
                    created.append({
                        "activity_id": activity.id,
                        "google_event_id": event["id"],
                        "summary": event.get("summary"),
                    })

                await self.db.commit()

                page_token = events_data.get("nextPageToken")
                if not page_token:
                    break

        credential.last_synced_at = datetime.now(UTC)
        await self.db.commit()
        return created

    async def _upsert_credential(self, user_id: int, token_data: dict) -> GoogleCalendarCredential:
        """Create or update Google Calendar credentials for a user."""
        existing = await self.get_credential(user_id)
        expiry = None
        if "expires_in" in token_data:
            expiry = datetime.now(UTC) + timedelta(seconds=token_data["expires_in"])

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

    def _activity_to_event(self, activity: Activity) -> dict[str, Any]:
        """Convert a CRM activity to a Google Calendar event payload."""
        event: dict[str, Any] = {
            "summary": activity.subject or "CRM Activity",
            "description": activity.description or "",
        }
        if activity.due_date:
            event["start"] = {"date": str(activity.due_date)}
            event["end"] = {"date": str(activity.due_date)}
        else:
            now = datetime.now(UTC).isoformat()
            event["start"] = {"dateTime": now}
            event["end"] = {"dateTime": now}
        return event

    def _event_to_activity(self, event: dict, user_id: int) -> Activity:
        """Convert a Google Calendar event to a CRM activity."""
        due_date = None
        scheduled_at = None
        start = event.get("start", {})
        if "dateTime" in start:
            scheduled_at = datetime.fromisoformat(start["dateTime"].replace("Z", "+00:00"))
            due_date = scheduled_at.date()
        elif "date" in start:
            due_date = datetime.strptime(start["date"], "%Y-%m-%d").date()

        # Google events aren't tied to a CRM entity; link them to the owning user
        # so the polymorphic (entity_type, entity_id) NOT NULL columns are satisfied.
        return Activity(
            activity_type="meeting",
            subject=event.get("summary", "Google Calendar Event"),
            description=event.get("description", ""),
            entity_type=ENTITY_TYPE_USERS,
            entity_id=user_id,
            scheduled_at=scheduled_at,
            due_date=due_date,
            is_completed=False,
            priority="normal",
            owner_id=user_id,
            assigned_to_id=user_id,
        )
