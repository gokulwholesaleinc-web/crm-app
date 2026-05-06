"""Shared invariants for entities that hang off an Opportunity.

Proposals, quotes, and payments all need the same rule: you cannot
attach a new billable artifact to an Opportunity that has been moved to
a Closed-Lost pipeline stage. Without this guard, a deal that everyone
treats as dead silently accumulates new proposals/quotes/payments,
which corrupts pipeline reporting and revenue forecasts.

The check raises ``ValueError`` so service-layer callers can let it
bubble naturally. Routers wrap their service calls with
``value_error_as_400`` to surface it as an HTTP 400.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def assert_opportunity_active(
    db: AsyncSession, opportunity_id: int, entity_label: str
) -> None:
    """Raise ValueError if the opportunity is on a Closed-Lost stage.

    `entity_label` is interpolated into the error message ("proposal",
    "quote", "payment", ...) so the user sees which create operation
    was rejected.

    Local import of the opportunities models avoids the import cycle
    between ``src.core`` and feature packages — same pattern used in
    ``src.core.entity_access``.
    """
    from src.opportunities.models import Opportunity, PipelineStage

    # Look up the opportunity directly first so "doesn't exist" and "has
    # no stage assigned" are distinguishable from "exists and not lost".
    # The previous join-based query swallowed all three into None, which
    # let an attacker pass a stale or deleted opportunity_id past the gate.
    opp_result = await db.execute(
        select(Opportunity.pipeline_stage_id).where(Opportunity.id == opportunity_id)
    )
    row = opp_result.one_or_none()
    if row is None:
        raise ValueError(f"Opportunity {opportunity_id} does not exist.")
    stage_id = row[0]
    if stage_id is None:
        # Stage hasn't been assigned yet — treat as active (cannot be Lost
        # without a stage). Logged elsewhere via the create flow if needed.
        return

    is_lost_result = await db.execute(
        select(PipelineStage.is_lost).where(PipelineStage.id == stage_id)
    )
    is_lost = is_lost_result.scalar_one_or_none()
    if is_lost is True:
        raise ValueError(
            f"Cannot create {entity_label} for an opportunity in a "
            f"Closed-Lost stage. Move the opportunity back to an active "
            f"stage first."
        )
