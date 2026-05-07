"""Notification event handler - creates in-app notifications when CRM events fire."""

import logging
from typing import Any

import src.database as _db
from src.notifications.models import Notification
from src.opportunities.models import PipelineStage

logger = logging.getLogger(__name__)


# Events for which "no recipient" is a real gap, not just an unhandled type.
# Used to gate the warn-log on dropped notifications so we don't spam logs
# for events we never wanted to notify about.
_RECIPIENT_REQUIRED_EVENTS = frozenset({
    "lead.created", "contact.created", "opportunity.stage_changed",
    "quote.sent", "quote.rejected",
    "proposal.sent", "proposal.rejected",
    "payment.received",
})


async def notification_event_handler(event_type: str, payload: dict[str, Any]) -> None:
    """Handle CRM events by creating in-app notifications.

    Registered with the event emitter for the events listed in main.py.
    On unrecoverable error, we log with full context (entity_id, user_id,
    traceback) so the operator can correlate a missing notification back
    to the originating event without grepping the request id by hand.
    """
    async with _db.async_session_maker() as session:
        try:
            notification = await _build_notification(session, event_type, payload)
            if notification:
                session.add(notification)
                await session.commit()
            elif event_type in _RECIPIENT_REQUIRED_EVENTS:
                logger.warning(
                    "Notification dropped (no recipient resolved): event=%s entity_id=%s user_id=%s",
                    event_type,
                    payload.get("entity_id"),
                    payload.get("user_id"),
                )
        except Exception as e:
            logger.error(
                "Notification event handler error for %s entity_id=%s user_id=%s: %s",
                event_type,
                payload.get("entity_id"),
                payload.get("user_id"),
                e,
                exc_info=True,
            )
            await session.rollback()


async def _build_notification(session, event_type: str, payload: dict[str, Any]):
    """Build a Notification from the event payload, or return None if not applicable."""
    user_id = payload.get("user_id")
    entity_id = payload.get("entity_id")
    entity_type = payload.get("entity_type")
    data = payload.get("data", {})

    if event_type in ("lead.created", "contact.created"):
        if not user_id:
            return None
        name = f"{data.get('first_name', '')} {data.get('last_name', '')}".strip() or "Unknown"
        label = "Lead" if event_type == "lead.created" else "Contact"
        return Notification(
            user_id=user_id,
            type=event_type.replace(".", "_"),
            title=f"New {label}",
            message=f"New {label.lower()}: {name}",
            entity_type=entity_type,
            entity_id=entity_id,
        )

    if event_type == "opportunity.stage_changed":
        opp_name = data.get("name", "Unknown")
        new_stage_id = data.get("new_stage_id")
        stage_name = "unknown"
        if new_stage_id:
            from sqlalchemy import select
            result = await session.execute(
                select(PipelineStage.name).where(PipelineStage.id == new_stage_id)
            )
            stage_name = result.scalar_one_or_none() or "unknown"
        return Notification(
            user_id=user_id,
            type="opportunity_stage_changed",
            title="Deal Stage Changed",
            message=f"Deal '{opp_name}' moved to {stage_name}",
            entity_type=entity_type,
            entity_id=entity_id,
        )

    # quote.{sent,rejected} / proposal.{sent,rejected}: always notify the
    # owner of the underlying record. Looking the owner up here (instead of
    # trusting payload.user_id, which is the actor for `.sent` and the owner
    # for `.rejected`) keeps the routing intent explicit. `accepted` events
    # are emitted but not subscribed here — out of audit scope.
    if event_type in ("quote.sent", "quote.rejected"):
        verb = event_type.split(".", 1)[1]
        number = data.get("quote_number") or "—"
        from src.quotes.models import Quote
        recipient_id = await _lookup_owner(session, Quote, entity_id)
        if not recipient_id:
            return None
        return Notification(
            user_id=recipient_id,
            type=event_type.replace(".", "_"),
            title=f"Quote {verb}",
            message=f"Quote {number} was {verb}",
            entity_type=entity_type,
            entity_id=entity_id,
        )

    if event_type in ("proposal.sent", "proposal.rejected"):
        verb = event_type.split(".", 1)[1]
        number = data.get("proposal_number") or "—"
        from src.proposals.models import Proposal
        recipient_id = await _lookup_owner(session, Proposal, entity_id)
        if not recipient_id:
            return None
        return Notification(
            user_id=recipient_id,
            type=event_type.replace(".", "_"),
            title=f"Proposal {verb}",
            message=f"Proposal {number} was {verb}",
            entity_type=entity_type,
            entity_id=entity_id,
        )

    if event_type == "payment.received":
        return Notification(
            user_id=user_id,
            type="payment_received",
            title="Payment received",
            message=f"Stripe payment processed ({data.get('event_type', 'payment')})",
            entity_type=entity_type,
            entity_id=entity_id,
        )

    return None


async def _lookup_owner(session, model, entity_id):
    """Return owner_id for a given model row, or None if the id is falsy/missing."""
    if not entity_id:
        return None
    from sqlalchemy import select

    result = await session.execute(select(model.owner_id).where(model.id == entity_id))
    return result.scalar_one_or_none()


async def create_completion_notification(
    user_id: int,
    title: str,
    message: str,
    entity_type: str,
    entity_id: int,
    notification_type: str = "completion",
) -> None:
    """Create a notification for campaign/sequence completion.

    Called directly from campaign/sequence services, not via the event bus.
    """
    async with _db.async_session_maker() as session:
        try:
            notification = Notification(
                user_id=user_id,
                type=notification_type,
                title=title,
                message=message,
                entity_type=entity_type,
                entity_id=entity_id,
            )
            session.add(notification)
            await session.commit()
        except Exception as e:
            logger.error("Failed to create completion notification: %s", e)
            await session.rollback()
