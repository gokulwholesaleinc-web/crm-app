"""Unit tests for the combined notification gate.

Verifies:

- ``gate_event`` returns the same answers as the legacy single-channel
  helpers it now backs.
- It only loads the prefs row once per call (the whole point of the
  refactor — was 2 round-trips per dispatcher).
- Asymmetric fail modes survive: in-app fails OPEN, email fails CLOSED
  on a recoverable DB error inside the gate.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.account.models import UserNotificationPrefs
from src.account.notification_gate import (
    gate_event,
    should_notify_in_app,
    should_send_email,
)


class TestGateEventParity:
    """gate_event must agree with the single-channel helpers."""

    async def test_no_prefs_row_allows_both(
        self, db_session: AsyncSession, test_user
    ):
        in_app, email = await gate_event(db_session, test_user.id, "lead_assigned")
        assert in_app is True
        assert email is True

        # Wrappers agree.
        assert await should_notify_in_app(db_session, test_user.id, "lead_assigned") is True
        assert await should_send_email(db_session, test_user.id, "lead_assigned") is True

    async def test_email_disabled_globally(
        self, db_session: AsyncSession, test_user
    ):
        prefs = UserNotificationPrefs(
            user_id=test_user.id,
            in_app_enabled=True,
            email_enabled=False,
        )
        db_session.add(prefs)
        await db_session.commit()

        in_app, email = await gate_event(db_session, test_user.id, "task_due")
        assert in_app is True
        assert email is False

    async def test_event_matrix_blocks_email_only(
        self, db_session: AsyncSession, test_user
    ):
        prefs = UserNotificationPrefs(
            user_id=test_user.id,
            event_matrix={"mention": {"email": False}},
        )
        db_session.add(prefs)
        await db_session.commit()

        in_app, email = await gate_event(db_session, test_user.id, "mention")
        assert in_app is True
        assert email is False

    async def test_email_digest_off_blocks_email(
        self, db_session: AsyncSession, test_user
    ):
        prefs = UserNotificationPrefs(
            user_id=test_user.id,
            email_digest="off",
        )
        db_session.add(prefs)
        await db_session.commit()

        in_app, email = await gate_event(db_session, test_user.id, "task_due")
        assert in_app is True
        assert email is False


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
        prefs = UserNotificationPrefs(user_id=test_user.id)
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
    """Asymmetric fail modes survive the refactor."""

    async def test_recoverable_load_error_falls_open_in_app_closed_email(
        self, db_session: AsyncSession, test_user, monkeypatch
    ):
        from src.account import notification_gate as gate_module

        async def boom(db, user_id):
            raise ValueError("simulated transient prefs read failure")

        monkeypatch.setattr(gate_module, "_load_prefs", boom)

        in_app, email = await gate_event(
            db_session, test_user.id, "contract_expiring"
        )
        assert in_app is True   # fail-open: extra bell is benign
        assert email is False   # fail-closed: opt-out violation is worse
