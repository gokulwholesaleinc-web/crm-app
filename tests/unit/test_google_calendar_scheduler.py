"""Tests for the Google Calendar background scheduler job.

Validates that _sync_google_calendars:
- Completes without raising when there are no credentials
- Isolates per-user failures so one revoked token does not abort the whole tick
"""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.auth.security import get_password_hash
from src.integrations.google_calendar.models import GoogleCalendarCredential


class TestSyncGoogleCalendarsEmpty:
    """Scheduler job should complete when no credentials exist."""

    @pytest.mark.asyncio
    async def test_completes_with_no_credentials(self, client):
        """Should complete without raising when GoogleCalendarCredential table is empty."""
        import src.database as db_module
        from src.core.scheduler import _sync_google_calendars

        # client fixture already patches async_session_maker to the test DB
        await _sync_google_calendars()


class TestSyncGoogleCalendarsIsolation:
    """Per-user failures must not abort the whole job."""

    @pytest.mark.asyncio
    async def test_swallows_per_user_sync_error(self, db_session: AsyncSession, client):
        """Should not raise even when sync_from_google raises for a user."""
        import src.database as db_module
        from src.core.scheduler import _sync_google_calendars
        from src.integrations.google_calendar.service import GoogleCalendarService

        user = User(
            email="gcal_scheduler_test@example.com",
            hashed_password=get_password_hash("testpass123"),
            full_name="GCal Test User",
            is_active=True,
            is_superuser=False,
        )
        db_session.add(user)
        await db_session.flush()

        credential = GoogleCalendarCredential(
            user_id=user.id,
            access_token="bogus_token",
            refresh_token=None,
            calendar_id="primary",
            is_active=True,
        )
        db_session.add(credential)
        await db_session.commit()

        original = GoogleCalendarService.sync_from_google

        async def _raise(self, user_id):
            raise RuntimeError("Simulated Google API failure (revoked token)")

        GoogleCalendarService.sync_from_google = _raise
        try:
            # Must not raise — per-user errors are caught and logged
            await _sync_google_calendars()
        finally:
            GoogleCalendarService.sync_from_google = original
