"""Phase-3 auto-send trigger: build + send an onboarding packet on accept.

Inlined into BOTH proposal-accept handlers (public + admin). It is best-effort
and NEVER raises — the callers run inside ``value_error_as_400`` (public) and
alongside a swallow-everything ``emit`` (admin), so a trigger failure must not
masquerade as a 400 or un-accept the proposal. Every failure mode lands on a
durable proposal ``Activity`` row instead (the ``Proposal`` model has no flag
field), so staff can see why no packet was created and send one manually.

Transaction ordering (§B.3): the CALLER commits the accept transition and
must call this trigger LAST — after every read of the ``proposal`` ORM object
(the response build / emit) — so the trigger's best-effort failure handling
(which may ``db.rollback()`` and thereby expire ``proposal``) can never break a
later read with a ``MissingGreenlet`` on the async session, and a failed
ACCEPT commit surfaces from the caller instead of being swallowed here. The
trigger itself only commits the packet+token it creates, between
``create_packet``'s flush and queuing the invite (``queue_email`` may send
synchronously, so the live link must be durable first). On a ``create_packet``
error it rolls back ONLY the half-built packet rows (a SAVEPOINT) and records
the reason on a durable proposal ``Activity``.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.activities.models import Activity
from src.contacts.models import Contact
from src.onboarding.completion_notices import queue_invite
from src.onboarding.packet_service import PacketService
from src.onboarding.selection_service import active_selection_template_ids
from src.proposals.models import Proposal

logger = logging.getLogger(__name__)


async def create_packet_and_send(
    db: AsyncSession, *, proposal: Proposal, actor_id: int | None
) -> None:
    """Build an onboarding packet from the proposal's selections + send it.

    NEVER raises. No-op (debug log) when the proposal has no active onboarding
    selections. Writes a durable proposal ``Activity`` (no packet) when there
    is no linked contact, no resolvable recipient email, or ``create_packet``
    fails (retired template / missing PDF / storage down).
    """
    # Capture the id up front: an unforeseen failure inside the inner helper can
    # leave the session mid-rollback, which expires the ``proposal`` ORM object —
    # reading ``proposal.id`` in the except would then sync-lazy-load and raise
    # ``MissingGreenlet`` on the async session, turning the swallowed error into a
    # 500. Log the captured int instead.
    proposal_id = proposal.id
    try:
        await _create_packet_and_send(db, proposal=proposal, actor_id=actor_id)
    except Exception:
        # Last-resort guard: the inner helper already converts known failure
        # modes to Activity rows; this catches anything unforeseen so the
        # accept can never 500/400 on the trigger.
        logger.exception(
            "Onboarding auto-send trigger crashed for proposal %s", proposal_id
        )
        # An unforeseen failure may leave the session in an aborted transaction
        # (asyncpg) — roll back so ``get_db``'s end-of-request commit doesn't
        # fail. Safe because the CALLER already committed the accept AND calls
        # this trigger LAST (after every ``proposal`` read), so expiring the ORM
        # object here breaks nothing and cannot un-accept the proposal.
        try:
            await db.rollback()
        except Exception:
            logger.exception("Onboarding trigger cleanup rollback failed")


async def _create_packet_and_send(
    db: AsyncSession, *, proposal: Proposal, actor_id: int | None
) -> None:
    # Capture the identifying primitives up front: a later ``db.rollback()``
    # (on a create_packet error) expires the ``proposal`` ORM object, so any
    # subsequent attribute read would trigger a sync lazy-load
    # (``MissingGreenlet`` on the async session).
    proposal_id = proposal.id
    owner_id = proposal.owner_id
    contact_id = proposal.contact_id
    company_id = proposal.company_id
    designated_signer_email = proposal.designated_signer_email

    # The accept is ALREADY committed by the caller before this trigger runs
    # (§B.3) — so we never commit it here, and a later best-effort rollback can
    # only discard the half-built packet rows, never the acceptance.
    template_ids = await active_selection_template_ids(db, proposal_id)
    if not template_ids:
        # A proposal with no onboarding selections shouldn't mint an empty
        # packet — this is the common case, so debug-log and return.
        logger.debug(
            "Proposal %s accepted with no onboarding selections; no packet.",
            proposal_id,
        )
        return

    if contact_id is None:
        await _skip_activity(
            db,
            proposal_id=proposal_id,
            owner_id=owner_id,
            actor_id=actor_id,
            description=(
                "Proposal accepted but has no linked contact; the onboarding "
                "packet was not created. Link a contact and send onboarding "
                "manually."
            ),
        )
        return

    recipient_email = await _resolve_recipient_email(
        db, designated_signer_email=designated_signer_email, contact_id=contact_id
    )
    if not recipient_email:
        await _skip_activity(
            db,
            proposal_id=proposal_id,
            owner_id=owner_id,
            actor_id=actor_id,
            description=(
                "Proposal accepted but no recipient email could be resolved "
                "for onboarding (no designated signer email and the linked "
                "contact has none). The onboarding packet was not created."
            ),
        )
        return

    recipient_name = await _resolve_recipient_name(db, contact_id)
    service = PacketService(db)
    # Build the packet inside a SAVEPOINT so a failure rolls back ONLY the
    # half-built packet rows — not the whole session (a session-wide rollback
    # would also discard any not-yet-committed caller side effects and is
    # avoided on the common error path).
    try:
        async with db.begin_nested():
            packet, raw_token = await service.create_packet(
                created_by_id=owner_id,
                contact_id=contact_id,
                recipient_email=recipient_email,
                template_ids=template_ids,
                recipient_name=recipient_name,
                company_id=company_id,
                proposal_id=proposal_id,
            )
    except Exception as exc:
        # PacketValidationError (retired template / missing PDF / esign
        # invariant) or PacketInfraError (storage down) — the savepoint already
        # rolled back the partial create; record the reason on a durable
        # Activity, no packet, and don't raise.
        await _skip_activity(
            db,
            proposal_id=proposal_id,
            owner_id=owner_id,
            actor_id=actor_id,
            description=(
                "Proposal accepted but the onboarding packet could not be "
                f"created: {exc}"
            ),
        )
        return

    # Commit the packet (+ token) BEFORE queuing the invite: a later rollback
    # would orphan a live link / dead token (``queue_email`` may send
    # synchronously, so the link must be durable first).
    await db.commit()
    packet_id = packet.id
    # queue_email is fail-soft (a send error becomes a failed EmailQueue row,
    # visible to staff), but a hard DB error queuing the row could still raise.
    # The packet is already committed (a live link exists) — so on a queue
    # failure, record a durable Activity pointing staff at "Resend invite"
    # rather than leaving a packet nobody was told about.
    try:
        queued = await queue_invite(db, packet=packet, raw_access_token=raw_token)
    except Exception as exc:
        await _skip_activity(
            db,
            proposal_id=proposal_id,
            owner_id=owner_id,
            actor_id=actor_id,
            description=(
                f"Onboarding packet {packet_id} was created but its invite "
                f"email could not be queued ({exc}); use Resend invite."
            ),
        )
        return
    if not queued:
        logger.debug(
            "Onboarding invite for packet %s already queued; not duplicated.",
            packet_id,
        )


async def _resolve_recipient_email(
    db: AsyncSession,
    *,
    designated_signer_email: str | None,
    contact_id: int | None,
) -> str | None:
    """designated_signer_email, else the linked contact's email (§B.1).

    Takes captured primitives (not the ORM object) and resolves the contact
    email by explicit query, so it is safe even after a commit/rollback expired
    the ``proposal`` object earlier in the flow.
    """
    if designated_signer_email:
        return designated_signer_email
    if contact_id is None:
        return None
    result = await db.execute(
        select(Contact.email).where(Contact.id == contact_id)
    )
    return result.scalar_one_or_none()


async def _resolve_recipient_name(
    db: AsyncSession, contact_id: int
) -> str | None:
    result = await db.execute(
        select(Contact.first_name, Contact.last_name).where(
            Contact.id == contact_id
        )
    )
    row = result.first()
    if row is None:
        return None
    name = f"{row[0] or ''} {row[1] or ''}".strip()
    return name or None


async def _skip_activity(
    db: AsyncSession,
    *,
    proposal_id: int,
    owner_id: int | None,
    actor_id: int | None,
    description: str,
) -> None:
    """Write + commit a durable proposal Activity recording why no packet was
    created. Committed on its own so the record survives even if the caller's
    request later rolls back (the accept itself is already committed)."""
    db.add(
        Activity(
            activity_type="note",
            subject="Onboarding auto-send skipped",
            description=description,
            entity_type="proposals",
            entity_id=proposal_id,
            is_completed=True,
            owner_id=owner_id,
            created_by_id=actor_id,
        )
    )
    await db.commit()
