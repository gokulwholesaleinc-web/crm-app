"""Notification event handler - creates in-app notifications when CRM events fire."""

import logging
from typing import Dict, Any

import src.database as _db
from src.notifications.models import Notification
from src.opportunities.models import PipelineStage

logger = logging.getLogger(__name__)


async def notification_event_handler(event_type: str, payload: Dict[str, Any]) -> None:
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


async def _build_notification(session, event_type: str, payload: Dict[str, Any]):
    """Build a Notification from the event payload, or return None if not applicable."""
    user_id = payload.get("user_id")
    entity_id = payload.get("entity_id")
    entity_type = payload.get("entity_type")
    data = payload.get("data", {})

    if not user_id:
        return None

    if event_type == "lead.created":
        first_name = data.get("first_name", "")
        last_name = data.get("last_name", "")
        name = f"{first_name} {last_name}".strip() or "Unknown"
        return Notification(
            user_id=user_id,
            type="lead_created",
            title="New Lead",
            message=f"New lead: {name}",
            entity_type=entity_type,
            entity_id=entity_id,
        )

    if event_type == "contact.created":
        first_name = data.get("first_name", "")
        last_name = data.get("last_name", "")
        name = f"{first_name} {last_name}".strip() or "Unknown"
        return Notification(
            user_id=user_id,
            type="contact_created",
            title="New Contact",
            message=f"New contact: {name}",
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

    return None


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
