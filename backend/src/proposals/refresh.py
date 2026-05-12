"""Refresh a Proposal's billing fields from its linked Quote."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.proposals.models import Proposal
from src.quotes.models import Quote

_LOCKED_STATUSES = frozenset({"signed", "accepted", "awaiting_payment", "paid"})


async def refresh_proposal_from_quote(
    db: AsyncSession,
    proposal: Proposal,
) -> Proposal:
    """
    Overwrite the proposal's amount / currency / payment_type / recurring fields
    with the current values from its linked quote.

    Raises ValueError for business-rule violations (caller wraps with 400/409).
    """
    if not proposal.quote_id:
        raise ValueError("Proposal is not linked to a quote")

    if proposal.status in _LOCKED_STATUSES:
        raise ValueError(
            f"Cannot refresh a proposal with status '{proposal.status}'"
        )

    result = await db.execute(select(Quote).where(Quote.id == proposal.quote_id))
    quote = result.scalar_one_or_none()
    if quote is None:
        raise LookupError(f"Linked quote {proposal.quote_id} no longer exists")

    proposal.amount = float(quote.total)
    proposal.currency = quote.currency
    proposal.payment_type = quote.payment_type
    proposal.recurring_interval = quote.recurring_interval
    proposal.recurring_interval_count = quote.recurring_interval_count

    await db.flush()
    await db.refresh(proposal)
    return proposal
