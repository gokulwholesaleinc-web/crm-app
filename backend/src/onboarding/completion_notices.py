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
from src.email.branded_templates import (
    TenantBrandingHelper,
    render_onboarding_invite_email,
    render_onboarding_ready_email,
)
from src.email.service import EmailService
from src.onboarding import tokens
from src.onboarding.models import OnboardingPacket
from src.onboarding.packet_errors import PacketRaceError
from src.onboarding.packet_service import DOWNLOAD_TOKEN_TTL, _now

logger = logging.getLogger(__name__)

# Stable, distinct invite subject (no ``purpose`` column — the subject is the
# mail-type discriminator for the idempotency predicate AND the staff delivery
# list). Deliberately different from the completion-notice subject ("Your
# onboarding documents are ready") so the two never collide.
INVITE_SUBJECT = "Action needed: complete your onboarding"

# Client "your signed documents are ready" notice — shared by the automatic
# post-completion send and the staff resend so the subject/body stay identical.
CLIENT_READY_SUBJECT = "Your onboarding documents are ready"


def _client_ready_body(branding: dict, client_link: str) -> str:
    """Branded "your signed documents are ready" body (download CTA pill)."""
    return render_onboarding_ready_email(
        branding, {"download_link": client_link, "expires_days": 7}
    )


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

    # Both notices are sent FROM the packet owner's connected Gmail (the staff
    # member who created the packet) — there is no transactional fallback sender.
    sender_id = packet.created_by_id
    # Tenant branding for the client-facing notice (matches the proposal e-mail
    # look). The owner notice stays plain — it's an internal staff message.
    branding = await TenantBrandingHelper.get_branding_for_user(db, sender_id)

    # Client download link (carries the raw download token — its only egress).
    if raw_download:
        client_link = f"{base_url}/onboarding/complete/{raw_download}"
        await _queue_once(
            email_service,
            db,
            packet_id=packet.id,
            to_email=packet.recipient_email,
            subject=CLIENT_READY_SUBJECT,
            body=_client_ready_body(branding, client_link),
            sent_by_id=sender_id,
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
            sent_by_id=sender_id,
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
    db: AsyncSession,
    packet_id: int,
    to_email: str,
    *,
    subject: str | None = None,
) -> bool:
    """True iff a non-failed onboarding e-mail already exists for (packet, to).

    The idempotency key shared by the completion notices, the staff resend,
    and the Phase-3 invite. Owner vs client is distinguished by ``to_email``
    (no ``purpose`` column); the invite (which shares ``to_email`` with the
    completion notice) is distinguished by ``subject`` — pass ``subject`` to
    narrow the predicate to that mail type. A previously-``failed`` row does
    NOT suppress a needed re-send.
    """
    from src.email.models import EmailQueue

    query = (
        select(EmailQueue.id)
        .where(EmailQueue.entity_type == "onboarding_packets")
        .where(EmailQueue.entity_id == packet_id)
        .where(EmailQueue.to_email == to_email)
        .where(EmailQueue.status != "failed")
        .limit(1)
    )
    if subject is not None:
        query = query.where(EmailQueue.subject == subject)
    existing = await db.execute(query)
    return existing.scalar_one_or_none() is not None


async def _queue_once(
    email_service: EmailService,
    db: AsyncSession,
    *,
    packet_id: int,
    to_email: str,
    subject: str,
    body: str,
    sent_by_id: int | None,
) -> None:
    """Queue an e-mail unless a non-failed one already exists for (packet, to,
    subject). Keying on ``subject`` is essential: a Phase-3 INVITE shares the
    recipient with the completion notice, so a subject-blind check would let the
    earlier invite suppress the (genuinely needed) completion e-mail.

    ``sent_by_id`` is the sending staff member — all outbound mail goes through
    their connected Gmail (``EmailService`` has no transactional fallback), so a
    ``None`` here marks the row failed instead of delivering. It must be the
    packet owner, never omitted."""
    if await _completion_email_exists(db, packet_id, to_email, subject=subject):
        return
    await email_service.queue_email(
        to_email=to_email,
        subject=subject,
        body=body,
        sent_by_id=sent_by_id,
        entity_type="onboarding_packets",
        entity_id=packet_id,
    )


async def queue_invite(
    db: AsyncSession,
    *,
    packet: OnboardingPacket,
    raw_access_token: str,
    suppress_if_exists: bool = True,
) -> bool:
    """Queue the onboarding INVITE e-mail carrying the access link.

    The raw access token is available only at create/resend time (only its
    hash is stored), so this is its one egress — mirrors ``access_url`` in
    ``packet_view.py``. Idempotent on (packet, recipient, INVITE_SUBJECT) when
    ``suppress_if_exists`` (the auto-send path): a non-failed invite row
    suppresses a duplicate. A staff resend passes ``suppress_if_exists=False``
    (deliberate action, like ``resend_completion_notices``). Returns True iff
    an e-mail was actually queued.
    """
    if suppress_if_exists and await _completion_email_exists(
        db, packet.id, packet.recipient_email, subject=INVITE_SUBJECT
    ):
        return False
    base_url = settings.FRONTEND_BASE_URL or "http://localhost:3000"
    access_link = f"{base_url}/onboarding/{raw_access_token}"
    branding = await TenantBrandingHelper.get_branding_for_user(
        db, packet.created_by_id
    )
    await EmailService(db).queue_email(
        to_email=packet.recipient_email,
        subject=INVITE_SUBJECT,
        body=render_onboarding_invite_email(
            branding,
            {
                "recipient_name": packet.recipient_name,
                "access_link": access_link,
                "expires_days": 30,
            },
        ),
        # Sent FROM the packet owner's Gmail (no fallback sender) — without this
        # the invite row can only ever fail, so the client never gets the link.
        sent_by_id=packet.created_by_id,
        entity_type="onboarding_packets",
        entity_id=packet.id,
    )
    return True


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
    """Re-queue the completion notices with a FRESH, working download link.

    The raw download token minted at completion is unrecoverable (only its hash
    is stored), so a resend mints a NEW download token, repoints the packet's
    ``download_token_hash`` at it (the previous emailed link dies), and embeds
    the working link — instead of the old "contact us" dead end. This is a
    deliberate staff action, so it is NOT suppressed by the completion-notice
    idempotency guard (that only protects the automatic post-completion send).
    """
    if packet.status != "completed":
        raise PacketRaceError("Packet is not completed; nothing to resend.")
    resent: list[str] = []
    email_service = EmailService(db)
    base_url = settings.FRONTEND_BASE_URL or "http://localhost:3000"

    raw_download = tokens.mint_token()
    packet.download_token_hash = tokens.hash_token(raw_download)
    packet.download_token_expires_at = _now() + DOWNLOAD_TOKEN_TTL
    # COMMIT (not flush) the rotated token BEFORE queuing — ``queue_email`` may
    # send synchronously, so the new token must be durable first; otherwise a
    # failing trailing request-commit could roll the hash back to the (already
    # unrecoverable) old value, leaving the recipient a dead emailed link.
    await db.commit()
    client_link = f"{base_url}/onboarding/complete/{raw_download}"
    branding = await TenantBrandingHelper.get_branding_for_user(
        db, packet.created_by_id
    )

    owner_email = await _owner_email(db, packet)
    for to_email, subject, body in _resend_targets(
        packet, owner_email, client_link, branding
    ):
        await email_service.queue_email(
            to_email=to_email,
            subject=subject,
            body=body,
            # Sent FROM the packet owner's Gmail (no fallback sender).
            sent_by_id=packet.created_by_id,
            entity_type="onboarding_packets",
            entity_id=packet.id,
        )
        resent.append(to_email)
    return resent


def _resend_targets(
    packet: OnboardingPacket,
    owner_email: str | None,
    client_link: str,
    branding: dict,
) -> list[tuple[str, str, str]]:
    targets = [
        (
            packet.recipient_email,
            CLIENT_READY_SUBJECT,
            _client_ready_body(branding, client_link),
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
