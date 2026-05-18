"""Unit tests for the combined notification gate.

Verifies:

- ``gate_event`` returns the same answers as the legacy single-channel
  helpers it now backs.
- It only loads the prefs row once per call (the whole point of the
  refactor — was 2 round-trips per dispatcher).
- Fail-closed on both channels: missing prefs row, missing event entry,
  or recoverable DB error all return (False, False).
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from src.account.models import UserNotificationPrefs
from src.account.notification_gate import (
    gate_event,
    should_notify_in_app,
    should_send_email,
)


class TestGateEventParity:
    """gate_event must agree with the single-channel helpers."""

    async def test_no_prefs_row_blocks_both(
        self, db_session: AsyncSession, test_user
    ):
        """Opt-in: no prefs row → both channels blocked."""
        in_app, email = await gate_event(db_session, test_user.id, "lead_assigned")
        assert in_app is False
        assert email is False

        # Wrappers agree.
        assert await should_notify_in_app(db_session, test_user.id, "lead_assigned") is False
        assert await should_send_email(db_session, test_user.id, "lead_assigned") is False

    async def test_email_disabled_globally(
        self, db_session: AsyncSession, test_user
    ):
        """email_enabled=False blocks email even when matrix allows it."""
        prefs = UserNotificationPrefs(
            user_id=test_user.id,
            in_app_enabled=True,
            email_enabled=False,
            event_matrix={"task_due": {"in_app": True, "email": True}},
        )
        db_session.add(prefs)
        await db_session.commit()

        in_app, email = await gate_event(db_session, test_user.id, "task_due")
        assert in_app is True
        assert email is False

    async def test_event_matrix_missing_in_app_key_blocks_in_app(
        self, db_session: AsyncSession, test_user
    ):
        """Opt-in: matrix present but in_app key absent → in_app blocked."""
        prefs = UserNotificationPrefs(
            user_id=test_user.id,
            in_app_enabled=True,
            email_enabled=True,
            event_matrix={"mention": {"email": False}},
        )
        db_session.add(prefs)
        await db_session.commit()

        in_app, email = await gate_event(db_session, test_user.id, "mention")
        # in_app key absent → False (opt-in: missing key = blocked)
        assert in_app is False
        assert email is False

    async def test_event_matrix_explicit_false_blocks_channel(
        self, db_session: AsyncSession, test_user
    ):
        """Matrix entry explicitly False blocks that channel."""
        prefs = UserNotificationPrefs(
            user_id=test_user.id,
            in_app_enabled=True,
            email_enabled=True,
            event_matrix={"mention": {"in_app": True, "email": False}},
        )
        db_session.add(prefs)
        await db_session.commit()

        in_app, email = await gate_event(db_session, test_user.id, "mention")
        assert in_app is True
        assert email is False

    async def test_email_digest_off_blocks_email(
        self, db_session: AsyncSession, test_user
    ):
        """email_digest=off blocks email regardless of matrix."""
        prefs = UserNotificationPrefs(
            user_id=test_user.id,
            in_app_enabled=True,
            email_enabled=True,
            email_digest="off",
            event_matrix={"task_due": {"in_app": True, "email": True}},
        )
        db_session.add(prefs)
        await db_session.commit()

        in_app, email = await gate_event(db_session, test_user.id, "task_due")
        assert in_app is True
        assert email is False

    async def test_both_channels_pass_when_fully_opted_in(
        self, db_session: AsyncSession, test_user
    ):
        """Fully opted-in prefs → both channels allowed."""
        prefs = UserNotificationPrefs(
            user_id=test_user.id,
            in_app_enabled=True,
            email_enabled=True,
            event_matrix={"lead_assigned": {"in_app": True, "email": True}},
        )
        db_session.add(prefs)
        await db_session.commit()

        in_app, email = await gate_event(db_session, test_user.id, "lead_assigned")
        assert in_app is True
        assert email is True

        assert await should_notify_in_app(db_session, test_user.id, "lead_assigned") is True
        assert await should_send_email(db_session, test_user.id, "lead_assigned") is True


class TestGateEventSingleRoundTrip:
    """Combined gate must hit the prefs table once per call.

    Pre-refactor, calling should_notify_in_app + should_send_email
    issued two separate ``SELECT user_notification_prefs`` queries per
    dispatcher. Notifications-heavy fan-outs (assignment + mention +
    activity-due in the same request) pre-paid 6 round-trips for
    nothing. The combined gate is supposed to be exactly one.
    """

    async def test_single_select_per_call(
        self, db_session: AsyncSession, test_user, monkeypatch
    ):
        prefs = UserNotificationPrefs(
            user_id=test_user.id,
            in_app_enabled=True,
            event_matrix={"lead_assigned": {"in_app": True}},
        )
        db_session.add(prefs)
        await db_session.commit()

        from src.account import notification_gate as gate_module

        load_count = 0
        original = gate_module._load_prefs

        async def counting_load(db, user_id):
            nonlocal load_count
            load_count += 1
            return await original(db, user_id)

        monkeypatch.setattr(gate_module, "_load_prefs", counting_load)

        await gate_event(db_session, test_user.id, "lead_assigned")
        assert load_count == 1


class TestGateEventFailModes:
    """Fail-closed on both channels for recoverable errors."""

    async def test_recoverable_load_error_falls_closed_both_channels(
        self, db_session: AsyncSession, test_user, monkeypatch
    ):
        """Any recoverable DB error during prefs load → (False, False).

        Both channels now fail closed: a transient prefs read failure
        should not leak a notification to a user who hasn't opted in.
        """
        from sqlalchemy.exc import OperationalError
        from src.account import notification_gate as gate_module

        async def boom(db, user_id):
            raise OperationalError("simulated transient prefs read failure", None, None)

        monkeypatch.setattr(gate_module, "_load_prefs", boom)

        in_app, email = await gate_event(
            db_session, test_user.id, "contract_expiring"
        )
        assert in_app is False   # fail-closed: no notification leaks
        assert email is False    # fail-closed: opt-out violation is worse
