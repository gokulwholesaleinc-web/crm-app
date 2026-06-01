"""Post-completion notice side effects (client + owner e-mails, timeline).

Split out of ``completion.py`` so the 3-phase orchestration there stays
focused. These run POST-COMMIT — the packet is already durably ``completed``
because ``queue_email`` may send before the request commits, so completion
state must be persisted first. Every send is idempotent: a non-failed
``EmailQueue`` row tagged ``entity_type='onboarding_packets'`` for the same
(packet, recipient) suppresses a duplicate (there is no ``purpose`` column —
owner vs client is distinguished by ``to_email``).
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.activities.models import Activity
from src.config import settings
from src.email.service import EmailService
from src.onboarding.models import OnboardingPacket
from src.onboarding.packet_errors import PacketRaceError

logger = logging.getLogger(__name__)


def _download_url(raw_download: str | None) -> str | None:
    """In-session download URL carrying the freshly minted raw download token.

    The completing client is authenticated in their bearer session, so the
    ``/complete`` response is their one in-session chance to fetch the signed
    PDFs (§5.2: link only post-gate / via e-mail). After this response the raw
    token is unrecoverable (only the hash is stored), so an idempotent
    re-complete returns ``None`` and the client uses the e-mailed link.
    """
    return f"/api/onboarding/download/{raw_download}" if raw_download else None


async def notify_after_commit(
    db: AsyncSession, *, packet: OnboardingPacket, raw_download: str | None
) -> None:
    """Best-effort post-commit notices.

    The packet is already committed ``completed``; a notice failure must NOT
    500 the request (the ``download_url`` in the response is the client's
    in-session link, independent of e-mail). Isolate + log so the completion
    still returns cleanly and the failure stays observable.
    """
    try:
        await _post_commit_notices(db, packet=packet, raw_download=raw_download)
    except Exception:
        logger.exception(
            "Onboarding packet %s completed but post-commit notices failed",
            packet.id,
        )


async def _post_commit_notices(
    db: AsyncSession, *, packet: OnboardingPacket, raw_download: str | None
) -> None:
    """Queue owner + client e-mails (idempotent) and write the timeline row."""
    email_service = EmailService(db)
    base_url = settings.FRONTEND_BASE_URL or "http://localhost:3000"

    # Client download link (carries the raw download token — its only egress).
    if raw_download:
        client_link = f"{base_url}/onboarding/complete/{raw_download}"
        await _queue_once(
            email_service,
            db,
            packet_id=packet.id,
            to_email=packet.recipient_email,
            subject="Your onboarding documents are ready",
            body=(
                "Thank you for completing your onboarding. You can download "
                f"your signed documents here:\n\n{client_link}\n\n"
                "This link expires in 7 days."
            ),
        )

    # Owner notice (the staff member who created the packet).
    owner_email = await _owner_email(db, packet)
    if owner_email:
        await _queue_once(
            email_service,
            db,
            packet_id=packet.id,
            to_email=owner_email,
            subject=f"Onboarding completed for contact #{packet.contact_id}",
            body=(
                f"The onboarding packet for contact #{packet.contact_id} has "
                "been completed and the signed documents are attached to the "
                "contact record."
            ),
        )

    # Contact timeline.
    db.add(
        Activity(
            activity_type="note",
            subject="Onboarding completed",
            description="Client completed and signed their onboarding documents.",
            entity_type="contacts",
            entity_id=packet.contact_id,
            owner_id=packet.created_by_id,
            created_by_id=packet.created_by_id,
        )
    )
    await db.flush()


async def _completion_email_exists(
    db: AsyncSession, packet_id: int, to_email: str
) -> bool:
    """True iff a non-failed onboarding e-mail already exists for (packet, to).

    The idempotency key shared by both the completion notices and the staff
    resend — owner vs client is distinguished by ``to_email`` (no ``purpose``
    column); a previously-``failed`` row does NOT suppress a needed re-send.
    """
    from src.email.models import EmailQueue

    existing = await db.execute(
        select(EmailQueue.id)
        .where(EmailQueue.entity_type == "onboarding_packets")
        .where(EmailQueue.entity_id == packet_id)
        .where(EmailQueue.to_email == to_email)
        .where(EmailQueue.status != "failed")
        .limit(1)
    )
    return existing.scalar_one_or_none() is not None


async def _queue_once(
    email_service: EmailService,
    db: AsyncSession,
    *,
    packet_id: int,
    to_email: str,
    subject: str,
    body: str,
) -> None:
    """Queue an e-mail unless a non-failed one already exists for (packet, to)."""
    if await _completion_email_exists(db, packet_id, to_email):
        return
    await email_service.queue_email(
        to_email=to_email,
        subject=subject,
        body=body,
        entity_type="onboarding_packets",
        entity_id=packet_id,
    )


async def _owner_email(db: AsyncSession, packet: OnboardingPacket) -> str | None:
    if packet.created_by_id is None:
        return None
    from src.auth.models import User

    result = await db.execute(
        select(User.email).where(User.id == packet.created_by_id)
    )
    return result.scalar_one_or_none()


async def resend_completion_notices(
    db: AsyncSession, *, packet: OnboardingPacket
) -> list[str]:
    """Idempotently re-queue the completion notices (only for completed)."""
    if packet.status != "completed":
        raise PacketRaceError("Packet is not completed; nothing to resend.")
    resent: list[str] = []
    email_service = EmailService(db)

    owner_email = await _owner_email(db, packet)
    # The raw download token is unrecoverable post-completion, so resend
    # points the client at the staff-shareable landing path instead.
    for to_email, subject, body in _resend_targets(packet, owner_email):
        if await _completion_email_exists(db, packet.id, to_email):
            continue
        await email_service.queue_email(
            to_email=to_email,
            subject=subject,
            body=body,
            entity_type="onboarding_packets",
            entity_id=packet.id,
        )
        resent.append(to_email)
    return resent


def _resend_targets(
    packet: OnboardingPacket, owner_email: str | None
) -> list[tuple[str, str, str]]:
    targets = [
        (
            packet.recipient_email,
            "Your onboarding documents are ready",
            "Your completed onboarding documents are available — contact us "
            "if you need the download link re-sent.",
        )
    ]
    if owner_email:
        targets.append(
            (
                owner_email,
                f"Onboarding completed for contact #{packet.contact_id}",
                f"The onboarding packet for contact #{packet.contact_id} is "
                "complete.",
            )
        )
    return targets
