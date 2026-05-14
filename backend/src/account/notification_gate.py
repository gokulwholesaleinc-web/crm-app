"""Pre-dispatch gate for notifications.

Dispatchers call ``should_notify_in_app`` / ``should_send_email`` before
queuing a notification or email. The matrix is opt-in: an event missing
from ``event_matrix``, a missing prefs row, or an empty matrix all
default to OFF. Users must explicitly enable notifications in
Settings → Notifications.

Defensive contract: unexpected exceptions are logged and we fail-closed
(return False) for both channels. A silent-drop here is the lesser evil
compared to leaking notifications to users who haven't opted in.
"""

from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.account.models import UserNotificationPrefs, UserPreferences

logger = logging.getLogger(__name__)

# Errors we deliberately fail-closed on at the gate boundary (prefs load +
# the outer gate_event try/except). KeyError and ValueError are intentionally
# excluded: they indicate a programming error inside the gate itself and should
# propagate so they're visible, not silently swallowed as "transient".
_GATE_RECOVERABLE = (SQLAlchemyError, TypeError, AttributeError)


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
    """Return True only when the event+channel is explicitly enabled.

    Opt-in contract: missing matrix, missing event entry, or missing
    channel key all return False. The caller must have an explicit
    ``{event_type: {channel: True}}`` entry to pass.
    """
    if not matrix:
        return False
    entry = matrix.get(event_type)
    if not entry:
        return False
    val = entry.get(channel)
    return False if val is None else bool(val)


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
        except ZoneInfoNotFoundError:
            logger.warning(
                "Unknown timezone %r for user %s; falling back to America/Chicago",
                tz_name,
                user_id,
            )
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

    Opt-in contract: missing prefs row → (False, False). Fail-closed on
    both channels for any recoverable error.
    """
    try:
        prefs = await _load_prefs(db, user_id)
    except _GATE_RECOVERABLE:
        logger.warning(
            "notification_gate.gate_event prefs-load failed for user_id=%s event=%s; defaulting (False, False)",
            user_id,
            event_type,
            exc_info=True,
        )
        return (False, False)

    if prefs is None:
        return (False, False)

    try:
        in_app_allowed = await _resolve_in_app(db, prefs, user_id, event_type)
    except _GATE_RECOVERABLE:
        logger.warning(
            "notification_gate.gate_event in-app resolve failed for user_id=%s event=%s; defaulting suppress",
            user_id,
            event_type,
            exc_info=True,
        )
        in_app_allowed = False

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
    opted out of email notifications gets one anyway, and for any
    cooldown-stamped event they then get locked out of re-notification
    for the cooldown window once the cooldown stamp lands. In-app
    fail-open is defensible (extra bell icon); email fail-open is a
    stated-preference violation. So a transient DB blip in the gate
    suppresses the send rather than leaking through. ``gate_event``
    carries this same fail-CLOSED behaviour.
    """
    _, email_allowed = await gate_event(db, user_id, event_type)
    return email_allowed
