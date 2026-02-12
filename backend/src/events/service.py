"""Simple event emitter for CRM domain events.

Allows registering handlers for event types and emitting events
that trigger all registered handlers.
"""

import logging
from typing import Callable, Dict, List, Any

logger = logging.getLogger(__name__)

# Event type constants
LEAD_CREATED = "lead.created"
LEAD_UPDATED = "lead.updated"
CONTACT_CREATED = "contact.created"
CONTACT_UPDATED = "contact.updated"
OPPORTUNITY_CREATED = "opportunity.created"
OPPORTUNITY_UPDATED = "opportunity.updated"
OPPORTUNITY_STAGE_CHANGED = "opportunity.stage_changed"
ACTIVITY_CREATED = "activity.created"
COMPANY_CREATED = "company.created"
COMPANY_UPDATED = "company.updated"

# Sales pipeline events
QUOTE_SENT = "quote.sent"
QUOTE_ACCEPTED = "quote.accepted"
PROPOSAL_SENT = "proposal.sent"
PROPOSAL_ACCEPTED = "proposal.accepted"
PAYMENT_RECEIVED = "payment.received"

# Registry: event_type -> list of async handler functions
_handlers: Dict[str, List[Callable]] = {}


def on(event_type: str, handler: Callable) -> None:
    """Register a handler for a given event type."""
    if event_type not in _handlers:
        _handlers[event_type] = []
    _handlers[event_type].append(handler)


def off(event_type: str, handler: Callable) -> None:
    """Unregister a handler for a given event type."""
    if event_type in _handlers:
        _handlers[event_type] = [h for h in _handlers[event_type] if h is not handler]


async def emit(event_type: str, payload: Dict[str, Any]) -> None:
    """Emit an event, calling all registered handlers.

    Handlers are called with (event_type, payload).
    Errors in individual handlers are logged but do not prevent other handlers from running.
    """
    handlers = _handlers.get(event_type, [])
    for handler in handlers:
        try:
            await handler(event_type, payload)
        except Exception as e:
            logger.error("Event handler error for %s: %s", event_type, e)


def clear_handlers() -> None:
    """Clear all registered handlers. Useful for testing."""
    _handlers.clear()


def get_handlers(event_type: str) -> List[Callable]:
    """Get handlers registered for an event type."""
    return _handlers.get(event_type, [])
