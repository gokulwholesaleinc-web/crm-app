"""Proposal→onboarding-template selection management (Phase 3, §4.7/§A).

The staff-curated, ordered set of onboarding templates a proposal carries.
On accept, ``trigger.create_packet_and_send`` reads these rows (ordered,
skipping retired templates) and mints a packet. Kept out of the template
service so the join-table concern stays self-contained and small.

The ``(proposal_id, display_order)`` unique constraint makes a naive per-row
``UPDATE display_order = N`` collide mid-reorder, so both ``set_selections``
and ``reorder`` write through a two-pass: bump every affected row to a
temporary high offset (flush), then write the final ``0..N-1`` values.
"""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.onboarding.models import (
    OnboardingTemplate,
    ProposalOnboardingSelection,
)
from src.onboarding.packet_errors import (
    PacketNotFoundError,
    PacketRaceError,
    PacketValidationError,
)
from src.proposals.models import Proposal

# A temporary offset larger than any realistic selection count, so the
# first pass of a reorder can't collide with a row's eventual final order.
_TEMP_ORDER_OFFSET = 1_000_000

# Proposal statuses at/after acceptance: the auto-send trigger has already
# read these selections and minted (or attempted) the onboarding packet, so the
# selection set is frozen — editing it now would silently diverge from what the
# client was actually sent. Mirrors the post-accept set in ``proposals/service``
# (``accepted`` → ``awaiting_payment`` → ``paid``).
_FROZEN_PROPOSAL_STATUSES = ("accepted", "awaiting_payment", "paid")


class SelectionService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_selections(
        self, proposal_id: int
    ) -> list[ProposalOnboardingSelection]:
        result = await self.db.execute(
            select(ProposalOnboardingSelection)
            .where(ProposalOnboardingSelection.proposal_id == proposal_id)
            .order_by(
                ProposalOnboardingSelection.display_order,
                ProposalOnboardingSelection.id,
            )
        )
        return list(result.scalars().all())

    async def set_selections(
        self,
        proposal_id: int,
        *,
        template_ids: list[int],
        actor_id: int | None,
    ) -> list[ProposalOnboardingSelection]:
        """Replace the whole ordered selection list for a proposal.

        Validates every template exists and is active (a retired template is a
        422 at SET time so staff get immediate feedback — the trigger skips
        inactive templates at fire time as a second guard). Duplicate
        ``template_ids`` are rejected (the unique constraint would also catch
        it, but a clean 422 is friendlier). Re-assigns ``display_order`` from
        the request order. Idempotent on the set of rows: the old rows are
        deleted and re-created from the new ordered list.
        """
        if len(set(template_ids)) != len(template_ids):
            raise PacketValidationError("Duplicate templates in the selection list.")
        await self._lock_proposal(proposal_id)
        await self._assert_templates_active(template_ids)

        # Replace wholesale: delete the old rows, flush so the unique-order
        # constraint is clear, then insert the new ordered list. Simpler and
        # collision-free vs diffing — the list is tiny (a handful of forms).
        await self.db.execute(
            delete(ProposalOnboardingSelection).where(
                ProposalOnboardingSelection.proposal_id == proposal_id
            )
        )
        await self.db.flush()
        for order, tid in enumerate(template_ids):
            self.db.add(
                ProposalOnboardingSelection(
                    proposal_id=proposal_id,
                    template_id=tid,
                    display_order=order,
                    created_by_id=actor_id,
                    updated_by_id=actor_id,
                )
            )
        await self.db.flush()
        return await self.list_selections(proposal_id)

    async def reorder(
        self,
        proposal_id: int,
        *,
        ordered_ids: list[int],
        actor_id: int | None,
    ) -> list[ProposalOnboardingSelection]:
        """Reassign ``display_order`` from ``ordered_ids`` (selection row ids).

        ``ordered_ids`` must be exactly the current selection ids (a strict
        permutation). The ``(proposal_id, display_order)`` unique constraint
        collides under a naive per-row UPDATE, so this bumps every row to a
        temporary high offset first (flush), then writes the final 0..N-1.
        """
        await self._lock_proposal(proposal_id)
        existing = await self.list_selections(proposal_id)
        by_id = {sel.id: sel for sel in existing}
        if set(ordered_ids) != set(by_id) or len(ordered_ids) != len(by_id):
            raise PacketValidationError(
                "ordered_ids must be exactly the current selection ids."
            )
        # Pass 1: move every row out of the final range to avoid a transient
        # duplicate (proposal_id, display_order) during the rewrite.
        for sel in existing:
            sel.display_order = _TEMP_ORDER_OFFSET + sel.id
        await self.db.flush()
        # Pass 2: write the final contiguous order.
        for order, sel_id in enumerate(ordered_ids):
            sel = by_id[sel_id]
            sel.display_order = order
            sel.updated_by_id = actor_id
        await self.db.flush()
        return await self.list_selections(proposal_id)

    async def remove(
        self, proposal_id: int, selection_id: int
    ) -> None:
        """Remove one selection row. 404 if it isn't on this proposal.

        Leaves a gap in ``display_order`` (e.g. 0,2 after removing 1) — that's
        harmless for the trigger (it orders by display_order, not the literal
        values) and avoids a needless renumber/flush. Staff reorder if they care.
        """
        await self._lock_proposal(proposal_id)
        result = await self.db.execute(
            select(ProposalOnboardingSelection)
            .where(ProposalOnboardingSelection.id == selection_id)
            .where(ProposalOnboardingSelection.proposal_id == proposal_id)
        )
        sel = result.scalar_one_or_none()
        if sel is None:
            raise PacketNotFoundError(
                f"Onboarding selection {selection_id} not found on this proposal."
            )
        await self.db.delete(sel)
        await self.db.flush()

    async def _lock_proposal(self, proposal_id: int) -> None:
        """Lock the proposal row and refuse edits once it has been accepted.

        Two jobs: (1) serialize concurrent selection mutations — two staff
        saving for the same proposal at once would race the ``(proposal_id,
        display_order)`` unique constraint into a raw IntegrityError / lost
        update, so a ``FOR UPDATE`` lock on the proposal row serializes them
        (dialect-aware ``with_for_update`` is a silent no-op on SQLite, so the
        test harness is unaffected). (2) Reject the edit if the proposal is
        already accepted — the auto-send trigger has already read these
        selections and minted the packet, so a late change would diverge from
        what the client was actually sent. Read the status under the SAME lock
        so a concurrent accept can't slip in between the check and the write.
        """
        result = await self.db.execute(
            select(Proposal.status)
            .where(Proposal.id == proposal_id)
            .with_for_update()
        )
        status = result.scalar_one_or_none()
        if status in _FROZEN_PROPOSAL_STATUSES:
            raise PacketRaceError(
                "This proposal has already been accepted; its onboarding "
                "documents are locked and can no longer be changed."
            )

    async def _assert_templates_active(self, template_ids: list[int]) -> None:
        """422 if any template is missing, retired, or has no PDF.

        A no-PDF template would pass this guard but blow up later in the
        trigger's ``create_packet`` (which requires a PDF), turning a clean
        SET-time 422 into a silent acceptance-time failure — so reject it here.
        """
        result = await self.db.execute(
            select(
                OnboardingTemplate.id,
                OnboardingTemplate.is_active,
                OnboardingTemplate.pdf_path,
            ).where(OnboardingTemplate.id.in_(template_ids))
        )
        by_id = {row[0]: (row[1], row[2]) for row in result.all()}
        for tid in template_ids:
            if tid not in by_id:
                raise PacketValidationError(f"Template {tid} not found.")
            is_active, pdf_path = by_id[tid]
            if not is_active:
                raise PacketValidationError(
                    f"Template {tid} is retired and cannot be selected."
                )
            if not pdf_path:
                raise PacketValidationError(
                    f"Template {tid} has no PDF uploaded yet and cannot be "
                    "selected."
                )


async def active_selection_template_ids(
    db: AsyncSession, proposal_id: int
) -> list[int]:
    """Ordered ``template_id``s for a proposal, dropping retired templates.

    The trigger's read path (§B): ``SELECT template_id ... ORDER BY
    display_order`` then drop any whose template ``is_active=false`` (a
    second guard — SET-time validation already rejects retired templates, but
    a template can be retired AFTER selection and before accept).
    """
    result = await db.execute(
        select(ProposalOnboardingSelection.template_id)
        .join(
            OnboardingTemplate,
            OnboardingTemplate.id == ProposalOnboardingSelection.template_id,
        )
        .where(ProposalOnboardingSelection.proposal_id == proposal_id)
        .where(OnboardingTemplate.is_active.is_(True))
        .order_by(
            ProposalOnboardingSelection.display_order,
            ProposalOnboardingSelection.id,
        )
    )
    return [row[0] for row in result.all()]
