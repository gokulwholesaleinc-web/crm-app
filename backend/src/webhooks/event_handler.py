"""Webhook event handler - delivers webhooks when CRM events occur."""

import logging
from typing import Dict, Any

from src.webhooks.service import WebhookService

logger = logging.getLogger(__name__)


async def webhook_event_handler(event_type: str, payload: Dict[str, Any]) -> None:
    """Handle CRM events by delivering to subscribed webhooks.

    Imports async_session_maker lazily so test fixtures that swap the
    session maker on src.database take effect for this handler too.
    """
    from src.database import async_session_maker

    async with async_session_maker() as session:
        try:
            service = WebhookService(session)
            webhooks = await service.get_active_webhooks_for_event(event_type)

            for webhook in webhooks:
                try:
                    await service.deliver_webhook(
                        webhook,
                        event_type,
                        {"event": event_type, "data": payload},
                    )
                except Exception as e:
                    logger.error(
                        "Failed to deliver webhook %s for event %s: %s",
                        webhook.id, event_type, e,
                    )

            await session.commit()
        except Exception as e:
            logger.error("Webhook event handler error for %s: %s", event_type, e)
            await session.rollback()
