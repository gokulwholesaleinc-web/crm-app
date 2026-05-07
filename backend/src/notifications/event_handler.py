"""Notification event handler - creates in-app notifications when CRM events fire."""

import logging
from typing import Any

import src.database as _db
from src.notifications.models import Notification
from src.opportunities.models import PipelineStage

logger = logging.getLogger(__name__)


async def notification_event_handler(event_type: str, payload: dict[str, Any]) -> None:
    """Handle CRM events by creating in-app notifications.

    Registered with the event emitter for LEAD_CREATED, CONTACT_CREATED,
    and OPPORTUNITY_STAGE_CHANGED events.
    """
    async with _db.async_session_maker() as session:
        try:
            notification = await _build_notification(session, event_type, payload)
            if notification:
                session.add(notification)
                await session.commit()
        except Exception as e:
            logger.error("Notification event handler error for %s: %s", event_type, e)
            await session.rollback()


async def _build_notification(session, event_type: str, payload: dict[str, Any]):
    """Build a Notification from the event payload, or return None if not applicable."""
    user_id = payload.get("user_id")
    entity_id = payload.get("entity_id")
    entity_type = payload.get("entity_type")
    data = payload.get("data", {})

    if not user_id:
        return None

    if event_type in ("lead.created", "contact.created"):
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

    if event_type in ("quote.sent", "quote.accepted", "quote.rejected"):
        qnum = data.get("quote_number") or "—"
        label = {"quote.sent": "Quote sent", "quote.accepted": "Quote accepted", "quote.rejected": "Quote rejected"}[event_type]
        msg = {"quote.sent": f"Quote {qnum} was sent",
               "quote.accepted": f"Quote {qnum} was accepted",
               "quote.rejected": f"Quote {qnum} was rejected"}[event_type]
        recipient_id = await _quote_owner(session, entity_id) if event_type in ("quote.sent", "quote.accepted") else user_id
        if not recipient_id:
            return None
        return Notification(
            user_id=recipient_id,
            type=event_type.replace(".", "_"),
            title=label,
            message=msg,
            entity_type=entity_type,
            entity_id=entity_id,
        )

    if event_type in ("proposal.sent", "proposal.accepted", "proposal.rejected"):
        pnum = data.get("proposal_number") or "—"
        label = {"proposal.sent": "Proposal sent", "proposal.accepted": "Proposal accepted", "proposal.rejected": "Proposal rejected"}[event_type]
        msg = {"proposal.sent": f"Proposal {pnum} was sent",
               "proposal.accepted": f"Proposal {pnum} was accepted",
               "proposal.rejected": f"Proposal {pnum} was rejected"}[event_type]
        recipient_id = await _proposal_owner(session, entity_id) if event_type in ("proposal.sent", "proposal.accepted") else user_id
        if not recipient_id:
            return None
        return Notification(
            user_id=recipient_id,
            type=event_type.replace(".", "_"),
            title=label,
            message=msg,
            entity_type=entity_type,
            entity_id=entity_id,
        )

    if event_type == "payment.received":
        if not user_id:
            return None
        return Notification(
            user_id=user_id,
            type="payment_received",
            title="Payment received",
            message=f"Stripe payment processed ({data.get('event_type', 'payment')})",
            entity_type=entity_type,
            entity_id=entity_id,
        )

    return None


async def _quote_owner(session, quote_id):
    if not quote_id:
        return None
    from sqlalchemy import select

    from src.quotes.models import Quote
    result = await session.execute(select(Quote.owner_id).where(Quote.id == quote_id))
    return result.scalar_one_or_none()


async def _proposal_owner(session, proposal_id):
    if not proposal_id:
        return None
    from sqlalchemy import select

    from src.proposals.models import Proposal
    result = await session.execute(select(Proposal.owner_id).where(Proposal.id == proposal_id))
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
