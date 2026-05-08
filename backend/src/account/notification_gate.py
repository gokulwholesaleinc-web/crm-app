"""Pre-dispatch gate for notifications.

Dispatchers call ``should_notify_in_app`` / ``should_send_email`` before
queuing a notification or email. The matrix is opt-out: an event missing
from ``event_matrix`` defaults to ON.

Defensive contract: any unexpected exception is logged and we return
True. A silent-drop bug here would hide all notifications for a user
without anything visible upstream — see the project's silent-failure
hunter rule.
"""

from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.account.models import UserNotificationPrefs, UserPreferences

logger = logging.getLogger(__name__)

# Errors we deliberately fall open on. Anything else (asyncio.CancelledError,
# memory errors, etc.) propagates so the request fails loudly. The fail-open
# choice covers shape errors on event_matrix (`TypeError`/`AttributeError` if
# someone hand-edits the row to a non-dict) and DB blips (`SQLAlchemyError`)
# — both are recoverable; silently dropping a notification a user wants is
# the worse failure mode the project's silent-failure rule is meant to catch.
_GATE_RECOVERABLE = (SQLAlchemyError, TypeError, AttributeError, KeyError, ValueError)


async def _load_prefs(
    db: AsyncSession, user_id: int
) -> UserNotificationPrefs | None:
    result = await db.execute(
        select(UserNotificationPrefs).where(
            UserNotificationPrefs.user_id == user_id
        )
    )
    return result.scalar_one_or_none()


async def _load_user_timezone(db: AsyncSession, user_id: int) -> str:
    result = await db.execute(
        select(UserPreferences.timezone).where(
            UserPreferences.user_id == user_id
        )
    )
    return result.scalar_one_or_none() or "America/Chicago"


def _matrix_allows(
    matrix: dict | None, event_type: str, channel: str
) -> bool:
    if not matrix:
        return True
    entry = matrix.get(event_type)
    if not entry:
        return True
    val = entry.get(channel)
    return True if val is None else bool(val)


def _in_quiet_window(now_hhmm: str, start: str, end: str) -> bool:
    """True if HH:MM ``now`` falls in [start, end), supporting wrap-around."""
    if start == end:
        return False
    if start < end:
        return start <= now_hhmm < end
    return now_hhmm >= start or now_hhmm < end


async def _resolve_in_app(
    db: AsyncSession,
    prefs: UserNotificationPrefs,
    user_id: int,
    event_type: str,
) -> bool:
    """In-app gate logic given an already-loaded prefs row.

    Quiet-hours TZ lookup is the only async leg; everything else is
    pure-Python on ``prefs`` so we don't hit the DB twice for matrix
    checks. Caller wraps the recoverable-error catch.
    """
    if not prefs.in_app_enabled:
        return False

    if not _matrix_allows(prefs.event_matrix, event_type, "in_app"):
        return False

    if (
        prefs.quiet_hours_enabled
        and prefs.quiet_hours_start
        and prefs.quiet_hours_end
    ):
        tz_name = await _load_user_timezone(db, user_id)
        try:
            tz = ZoneInfo(tz_name)
        except _GATE_RECOVERABLE:
            tz = ZoneInfo("America/Chicago")
        now_hhmm = datetime.now(tz).strftime("%H:%M")
        if _in_quiet_window(
            now_hhmm, prefs.quiet_hours_start, prefs.quiet_hours_end
        ):
            return False

    return True


async def gate_event(
    db: AsyncSession, user_id: int, event_type: str
) -> tuple[bool, bool]:
    """Return ``(in_app_allowed, email_allowed)`` from a single prefs load.

    Combined helper halves the per-event DB chatter that calling
    :func:`should_notify_in_app` and :func:`should_send_email`
    back-to-back used to incur (one ``SELECT user_notification_prefs``
    round-trip each).

    Preserves the asymmetric fail modes:
    - in-app: fail-OPEN on recoverable errors (extra bell is benign)
    - email: fail-CLOSED on recoverable errors (silent opt-out violation
      is the worse failure mode, especially under cooldown stamping)
    """
    try:
        prefs = await _load_prefs(db, user_id)
    except _GATE_RECOVERABLE:
        logger.warning(
            "notification_gate.gate_event prefs-load failed for user_id=%s event=%s; defaulting (allow_in_app=True, allow_email=False)",
            user_id,
            event_type,
            exc_info=True,
        )
        return (True, False)

    if prefs is None:
        # New users without a prefs row: allow both. Email default-allow
        # mirrors the pre-refactor single-channel ``should_send_email``.
        return (True, True)

    try:
        in_app_allowed = await _resolve_in_app(db, prefs, user_id, event_type)
    except _GATE_RECOVERABLE:
        logger.warning(
            "notification_gate.gate_event in-app resolve failed for user_id=%s event=%s; defaulting allow",
            user_id,
            event_type,
            exc_info=True,
        )
        in_app_allowed = True

    email_allowed = (
        prefs.email_enabled
        and prefs.email_digest != "off"
        and _matrix_allows(prefs.event_matrix, event_type, "email")
    )

    return (in_app_allowed, email_allowed)


async def should_notify_in_app(
    db: AsyncSession, user_id: int, event_type: str
) -> bool:
    """Single-channel in-app gate. Prefer :func:`gate_event` when both
    channels are checked — this wrapper exists for callers that genuinely
    only need one side (e.g. flows that don't have an email surface).
    """
    in_app_allowed, _ = await gate_event(db, user_id, event_type)
    return in_app_allowed


async def should_send_email(
    db: AsyncSession, user_id: int, event_type: str
) -> bool:
    """Single-channel email gate.

    The cost of false-allow on email is real: a user who explicitly
    opted out of email notifications gets one anyway, *and* — for
    cooldown-stamped events like ``contract_expiring`` — they then get
    locked out of re-notification for the cooldown window once the
    cooldown stamp lands. In-app fail-open is defensible (extra bell
    icon); email fail-open is a stated-preference violation. So a
    transient DB blip in the gate suppresses the send rather than
    leaking through. ``gate_event`` carries this same fail-CLOSED
    behaviour.
    """
    _, email_allowed = await gate_event(db, user_id, event_type)
    return email_allowed
