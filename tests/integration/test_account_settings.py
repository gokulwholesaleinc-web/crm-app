"""Integration tests for /api/account/notifications + /api/account/preferences.

Covers the account-prefs CRUD surface and the notification gate the
dispatchers consult before queuing notifications.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from src.account.notification_gate import (
    _in_quiet_window,
    should_notify_in_app,
    should_send_email,
)
from src.account.schemas import (
    AccountPreferencesUpdate,
    NotificationPrefsUpdate,
)
from src.account.service import AccountPrefsService
from src.auth.models import User
from src.auth.security import create_access_token


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(data={'sub': str(user.id)})}"}


# ---------------------------------------------------------------------------
# /api/account/notifications
# ---------------------------------------------------------------------------


class TestNotificationPrefsRoutes:
    async def test_get_creates_defaults_on_first_call(
        self, client: AsyncClient, test_user: User
    ):
        """First GET lazy-creates the row with opt-in defaults (all OFF)."""
        resp = await client.get(
            "/api/account/notifications", headers=_headers(test_user)
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["in_app_enabled"] is False
        assert body["email_enabled"] is False
        assert body["email_digest"] == "instant"
        assert body["quiet_hours_enabled"] is False
        assert body["event_matrix"] == {}

    async def test_no_auth_returns_401(self, client: AsyncClient):
        """Unauthenticated GET is rejected."""
        resp = await client.get("/api/account/notifications")
        assert resp.status_code == 401

    async def test_put_partial_update_persists(
        self, client: AsyncClient, test_user: User
    ):
        """PUT with a subset of fields updates only those fields; untouched fields keep defaults."""
        resp = await client.put(
            "/api/account/notifications",
            json={"email_digest": "daily_8am", "in_app_enabled": False},
            headers=_headers(test_user),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["email_digest"] == "daily_8am"
        assert body["in_app_enabled"] is False
        assert body["email_enabled"] is False

    async def test_put_event_matrix_deep_merges(
        self, client: AsyncClient, test_user: User
    ):
        """Toggling one event leaves siblings intact."""
        await client.put(
            "/api/account/notifications",
            json={
                "event_matrix": {
                    "lead_assigned": {"in_app": True, "email": False},
                    "payment_received": {"in_app": True, "email": True},
                }
            },
            headers=_headers(test_user),
        )

        resp = await client.put(
            "/api/account/notifications",
            json={"event_matrix": {"lead_assigned": {"email": True}}},
            headers=_headers(test_user),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["event_matrix"]["lead_assigned"] == {
            "in_app": True,
            "email": True,
        }
        # payment_received survived the partial write
        assert body["event_matrix"]["payment_received"] == {
            "in_app": True,
            "email": True,
        }

    async def test_put_rejects_invalid_email_digest(
        self, client: AsyncClient, test_user: User
    ):
        """Validator rejects unknown digest mode."""
        resp = await client.put(
            "/api/account/notifications",
            json={"email_digest": "weekly"},
            headers=_headers(test_user),
        )
        assert resp.status_code == 422

    async def test_put_rejects_invalid_quiet_hours_format(
        self, client: AsyncClient, test_user: User
    ):
        """quiet_hours_start must be HH:MM."""
        resp = await client.put(
            "/api/account/notifications",
            json={"quiet_hours_start": "9am"},
            headers=_headers(test_user),
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# /api/account/preferences
# ---------------------------------------------------------------------------


class TestPreferencesRoutes:
    async def test_get_creates_defaults(self, client: AsyncClient, test_user: User):
        """First GET lazy-creates the prefs row with documented defaults."""
        resp = await client.get(
            "/api/account/preferences", headers=_headers(test_user)
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["timezone"] == "America/Chicago"
        assert body["locale"] == "en-US"
        assert body["theme"] == "system"
        assert body["default_landing"] == "/dashboard"
        assert body["guide_progress"] == {
            "completed_guide_ids": [],
            "first_run_dismissed_at": None,
            "disabled_at": None,
            "last_reset_at": None,
        }

    async def test_put_accepts_known_timezone(
        self, client: AsyncClient, test_user: User
    ):
        """A real IANA tz round-trips."""
        resp = await client.put(
            "/api/account/preferences",
            json={"timezone": "Europe/London"},
            headers=_headers(test_user),
        )
        assert resp.status_code == 200
        assert resp.json()["timezone"] == "Europe/London"

    async def test_put_rejects_unknown_timezone(
        self, client: AsyncClient, test_user: User
    ):
        """Made-up tz is rejected before persistence."""
        resp = await client.put(
            "/api/account/preferences",
            json={"timezone": "Atlantis/Lost"},
            headers=_headers(test_user),
        )
        assert resp.status_code == 422

    async def test_put_rejects_invalid_theme(
        self, client: AsyncClient, test_user: User
    ):
        """theme must be one of the documented values."""
        resp = await client.put(
            "/api/account/preferences",
            json={"theme": "neon"},
            headers=_headers(test_user),
        )
        assert resp.status_code == 422

    async def test_put_persists_guide_progress_per_account(
        self, client: AsyncClient, test_user: User
    ):
        """Guide completion/dismissal state is account-backed, not browser-local only."""
        resp = await client.put(
            "/api/account/preferences",
            json={
                "guide_progress": {
                    "completed_guide_ids": ["pipeline-tour", "dashboard-tour", "pipeline-tour"],
                    "first_run_dismissed_at": "2026-05-18T20:00:00.000Z",
                    "disabled_at": "2026-05-18T20:05:00.000Z",
                }
            },
            headers=_headers(test_user),
        )

        assert resp.status_code == 200
        assert resp.json()["guide_progress"] == {
            "completed_guide_ids": ["dashboard-tour", "pipeline-tour"],
            "first_run_dismissed_at": "2026-05-18T20:00:00.000Z",
            "disabled_at": "2026-05-18T20:05:00.000Z",
            "last_reset_at": None,
        }

        roundtrip = await client.get(
            "/api/account/preferences", headers=_headers(test_user)
        )
        assert roundtrip.status_code == 200
        assert roundtrip.json()["guide_progress"]["completed_guide_ids"] == [
            "dashboard-tour",
            "pipeline-tour",
        ]

    async def test_put_rejects_oversized_guide_progress(
        self, client: AsyncClient, test_user: User
    ):
        """Reject unexpectedly huge guide ids before they can bloat the prefs row."""
        resp = await client.put(
            "/api/account/preferences",
            json={"guide_progress": {"completed_guide_ids": ["x" * 121]}},
            headers=_headers(test_user),
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# notification_gate.should_notify_in_app
# ---------------------------------------------------------------------------


class TestNotificationGate:
    async def test_default_block_when_no_prefs_row(
        self, db_session: AsyncSession, test_user: User
    ):
        """A user who never opened settings receives no notifications (opt-in contract)."""
        assert (
            await should_notify_in_app(db_session, test_user.id, "lead_assigned")
            is False
        )

    async def test_master_switch_off_blocks_event(
        self, db_session: AsyncSession, test_user: User
    ):
        """Top-level in_app_enabled=False shorts out the gate."""
        service = AccountPrefsService(db_session)
        await service.update_notification_prefs(
            test_user.id, NotificationPrefsUpdate(in_app_enabled=False)
        )
        assert (
            await should_notify_in_app(db_session, test_user.id, "lead_assigned")
            is False
        )

    async def test_per_event_opt_in_allows_only_that_event(
        self, db_session: AsyncSession, test_user: User
    ):
        """Per-event opt-in allows just that event; events absent from matrix stay silent."""
        service = AccountPrefsService(db_session)
        await service.update_notification_prefs(
            test_user.id,
            NotificationPrefsUpdate(
                in_app_enabled=True,
                event_matrix={"payment_received": {"in_app": True}},
            ),
        )
        assert (
            await should_notify_in_app(db_session, test_user.id, "payment_received")
            is True
        )
        # lead_assigned is absent from the matrix → blocked under opt-in contract
        assert (
            await should_notify_in_app(db_session, test_user.id, "lead_assigned")
            is False
        )

    async def test_quiet_hours_block_in_window(
        self, db_session: AsyncSession, test_user: User
    ):
        """A quiet window straddling 'now' (in user tz) blocks delivery."""
        # Pin user tz to UTC so we can aim quiet_hours at the current minute
        prefs_svc = AccountPrefsService(db_session)
        await prefs_svc.update_preferences(
            test_user.id, AccountPreferencesUpdate(timezone="UTC")
        )
        now = datetime.now(ZoneInfo("UTC"))
        start = (now - timedelta(minutes=30)).strftime("%H:%M")
        end = (now + timedelta(minutes=30)).strftime("%H:%M")
        await prefs_svc.update_notification_prefs(
            test_user.id,
            NotificationPrefsUpdate(
                quiet_hours_enabled=True,
                quiet_hours_start=start,
                quiet_hours_end=end,
            ),
        )
        assert (
            await should_notify_in_app(db_session, test_user.id, "lead_assigned")
            is False
        )

    async def test_email_gate_master_switch(
        self, db_session: AsyncSession, test_user: User
    ):
        """email_enabled=False blocks every email channel."""
        service = AccountPrefsService(db_session)
        await service.update_notification_prefs(
            test_user.id, NotificationPrefsUpdate(email_enabled=False)
        )
        assert (
            await should_send_email(db_session, test_user.id, "payment_received")
            is False
        )

    async def test_email_gate_digest_off(
        self, db_session: AsyncSession, test_user: User
    ):
        """email_digest='off' blocks every event email."""
        service = AccountPrefsService(db_session)
        await service.update_notification_prefs(
            test_user.id, NotificationPrefsUpdate(email_digest="off")
        )
        assert (
            await should_send_email(db_session, test_user.id, "lead_assigned")
            is False
        )


class TestQuietWindowMath:
    def test_normal_window(self):
        """Same-day window 09:00-17:00 contains noon, excludes 18:00."""
        assert _in_quiet_window("12:00", "09:00", "17:00") is True
        assert _in_quiet_window("18:00", "09:00", "17:00") is False

    def test_wrap_around_window(self):
        """22:00-08:00 wraps midnight: 23:00 and 03:00 are in, 12:00 is out."""
        assert _in_quiet_window("23:00", "22:00", "08:00") is True
        assert _in_quiet_window("03:00", "22:00", "08:00") is True
        assert _in_quiet_window("12:00", "22:00", "08:00") is False

    def test_empty_window(self):
        """start==end means no window — never quiet."""
        assert _in_quiet_window("12:00", "09:00", "09:00") is False
