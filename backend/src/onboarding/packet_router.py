"""Staff (authenticated) packet routes (Phase 2, §3.1).

Thin routes delegating to ``PacketService`` / ``completion``. Every route
gates on the packet's contact via ``require_entity_access`` (data-scope) so a
sales rep can't act on another owner's contact. Reads gate ``contacts.read``,
create gates ``contacts.create``, mutations gate ``contacts.update``.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from src.auth.models import User
from src.core.constants import HTTPStatus
from src.core.data_scope import DataScope, get_data_scope
from src.core.entity_access import require_entity_access
from src.core.permissions import require_permission
from src.core.router_utils import DBSession, raise_not_found
from src.onboarding import completion
from src.onboarding.packet_schemas import (
    PacketCreate,
    PacketResponse,
    PurgeResult,
    ResendResult,
)
from src.onboarding.packet_service import PacketService
from src.onboarding.packet_view import build_packet_response
from src.onboarding.validation import packet_errors_mapped

router = APIRouter(prefix="/api/onboarding", tags=["onboarding-packets"])

ReadUser = Annotated[User, Depends(require_permission("contacts", "read"))]
CreateUser = Annotated[User, Depends(require_permission("contacts", "create"))]
UpdateUser = Annotated[User, Depends(require_permission("contacts", "update"))]
Scope = Annotated[DataScope, Depends(get_data_scope)]


async def _load_packet_checked(
    db, packet_id: int, current_user: User, data_scope: DataScope
) -> tuple[PacketService, "object"]:
    service = PacketService(db)
    packet = await service.get_packet(packet_id)
    if packet is None:
        raise_not_found("Onboarding packet", packet_id)
    await require_entity_access(
        db, "contacts", packet.contact_id, current_user, data_scope
    )
    return service, packet


@router.post(
    "/packets", response_model=PacketResponse, status_code=HTTPStatus.CREATED
)
async def create_packet(
    data: PacketCreate,
    current_user: CreateUser,
    db: DBSession,
    data_scope: Scope,
):
    """Create a packet + frozen docs; return the one-time ``access_url``."""
    await require_entity_access(
        db, "contacts", data.contact_id, current_user, data_scope
    )
    # The optional company/proposal links are persisted on the packet and the
    # company name is surfaced to the recipient (disclosure / prefill / public
    # response), so a scoped caller must be allowed to reference them too —
    # otherwise they could attach (and leak) another owner's company/proposal.
    if data.company_id is not None:
        await require_entity_access(
            db, "companies", data.company_id, current_user, data_scope
        )
    if data.proposal_id is not None:
        await require_entity_access(
            db, "proposals", data.proposal_id, current_user, data_scope
        )
    service = PacketService(db)
    with packet_errors_mapped():
        packet, raw_token = await service.create_packet(
            created_by_id=current_user.id,
            contact_id=data.contact_id,
            recipient_email=str(data.recipient_email),
            recipient_name=data.recipient_name,
            company_id=data.company_id,
            proposal_id=data.proposal_id,
            template_ids=data.template_ids,
            requires_esign_override=data.requires_esign_override,
        )
    return await build_packet_response(db, service, packet, raw_token=raw_token)


@router.get("/packets", response_model=list[PacketResponse])
async def list_packets(
    current_user: ReadUser,
    db: DBSession,
    data_scope: Scope,
    contact_id: int = Query(...),
):
    """List a contact's packets (+ interim PII sweep). NO tokens echoed."""
    await require_entity_access(
        db, "contacts", contact_id, current_user, data_scope
    )
    service = PacketService(db)
    packets = await service.list_packets(contact_id)
    return [await build_packet_response(db, service, p) for p in packets]


@router.get("/packets/{packet_id}", response_model=PacketResponse)
async def get_packet(
    packet_id: int,
    current_user: ReadUser,
    db: DBSession,
    data_scope: Scope,
):
    service, packet = await _load_packet_checked(
        db, packet_id, current_user, data_scope
    )
    return await build_packet_response(db, service, packet)


@router.post("/packets/{packet_id}/revoke", response_model=PacketResponse)
async def revoke_packet(
    packet_id: int,
    current_user: UpdateUser,
    db: DBSession,
    data_scope: Scope,
):
    service, packet = await _load_packet_checked(
        db, packet_id, current_user, data_scope
    )
    with packet_errors_mapped():
        packet = await service.revoke_packet(packet, revoked_by_id=current_user.id)
    return await build_packet_response(db, service, packet)


@router.post("/packets/{packet_id}/retry-completion", response_model=PacketResponse)
async def retry_completion(
    packet_id: int,
    current_user: UpdateUser,
    db: DBSession,
    data_scope: Scope,
):
    """Re-run Phase B/C for a completion_failed or stuck-completing packet."""
    service, packet = await _load_packet_checked(
        db, packet_id, current_user, data_scope
    )
    with packet_errors_mapped():
        await completion.retry_completion(db, packet=packet)
    # Reload to reflect the new status.
    packet = await service.get_packet(packet_id)
    return await build_packet_response(db, service, packet)


@router.post(
    "/packets/{packet_id}/resend-completion-notice", response_model=ResendResult
)
async def resend_completion_notice(
    packet_id: int,
    current_user: UpdateUser,
    db: DBSession,
    data_scope: Scope,
):
    service, packet = await _load_packet_checked(
        db, packet_id, current_user, data_scope
    )
    with packet_errors_mapped():
        resent = await completion.resend_completion_notices(db, packet=packet)
    return ResendResult(resent=resent)


@router.post("/packets/{packet_id}/purge-pii", response_model=PurgeResult)
async def purge_pii(
    packet_id: int,
    current_user: UpdateUser,
    db: DBSession,
    data_scope: Scope,
):
    service, packet = await _load_packet_checked(
        db, packet_id, current_user, data_scope
    )
    await service.purge_pii(packet)
    return PurgeResult(purged=True)
