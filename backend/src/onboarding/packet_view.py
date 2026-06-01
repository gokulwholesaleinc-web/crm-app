"""Staff PacketResponse assembly (doc summaries + live e-mail delivery).

Kept out of the router so the route module stays thin and the EmailQueue
join lives next to the schema it fills. Tokens are never surfaced here; the
one-time raw ``access_url`` is passed in only on the create path.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.email.models import EmailQueue
from src.onboarding.models import OnboardingPacket
from src.onboarding.packet_schemas import (
    PacketDelivery,
    PacketDocumentSummary,
    PacketResponse,
)
from src.onboarding.packet_service import PacketService, _mask_email


async def build_packet_response(
    db: AsyncSession,
    service: PacketService,
    packet: OnboardingPacket,
    *,
    raw_token: str | None = None,
) -> PacketResponse:
    documents = await service.load_documents(packet.id)
    deliveries = await _load_deliveries(db, packet.id)
    access_url = None
    if raw_token is not None:
        base_url = settings.FRONTEND_BASE_URL or "http://localhost:3000"
        access_url = f"{base_url}/onboarding/{raw_token}"
    return PacketResponse(
        id=packet.id,
        contact_id=packet.contact_id,
        company_id=packet.company_id,
        proposal_id=packet.proposal_id,
        status=packet.status,
        recipient_email_masked=_mask_email(packet.recipient_email),
        recipient_name=packet.recipient_name,
        document_count=len(documents),
        token_expires_at=packet.token_expires_at,
        completed_at=packet.completed_at,
        first_opened_at=packet.first_opened_at,
        created_at=packet.created_at,
        documents=[PacketDocumentSummary.model_validate(d) for d in documents],
        emails=deliveries,
        access_url=access_url,
    )


async def _load_deliveries(db: AsyncSession, packet_id: int) -> list[PacketDelivery]:
    rows = await db.execute(
        select(EmailQueue)
        .where(EmailQueue.entity_type == "onboarding_packets")
        .where(EmailQueue.entity_id == packet_id)
        .order_by(EmailQueue.created_at.desc())
    )
    return [
        PacketDelivery(
            id=r.id,
            to_email=_mask_email(r.to_email),
            subject=r.subject,
            status=r.status,
            created_at=r.created_at,
        )
        for r in rows.scalars().all()
    ]
