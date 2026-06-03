"""Staff (authenticated) packet routes (Phase 2, §3.1).

Thin routes delegating to ``PacketService`` / ``completion``. Every route
gates on the packet's contact via ``require_entity_access`` (data-scope) so a
sales rep can't act on another owner's contact. Reads gate ``contacts.read``,
create gates ``contacts.create``, mutations gate ``contacts.update``.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from src.auth.models import User
from src.core.constants import HTTPStatus
from src.core.data_scope import DataScope, get_data_scope
from src.core.entity_access import require_entity_access
from src.core.permissions import require_permission
from src.core.router_utils import DBSession, raise_not_found
from src.onboarding import completion, crypto
from src.onboarding.models import (
    OnboardingPacketDocument,
    OnboardingSecretValue,
)
from src.onboarding.packet_schemas import (
    PacketCreate,
    PacketResponse,
    PurgeResult,
    ResendResult,
    SecretValue,
    SecretValuesResponse,
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


@router.post("/packets/{packet_id}/resend", response_model=PacketResponse)
async def resend_invite(
    packet_id: int,
    current_user: UpdateUser,
    db: DBSession,
    data_scope: Scope,
):
    """Re-mint the access link + re-queue the onboarding invite (§C.2).

    Allowed for active/opened/in_progress/expired; 409 for terminal states.
    Commits the fresh token BEFORE queuing the invite (``queue_email`` may
    send synchronously, so the link must be durable first — same rule as
    ``resend_completion_notices``). The invite is NOT suppressed by the
    idempotency guard (deliberate staff action).
    """
    from src.onboarding.completion_notices import queue_invite

    service, packet = await _load_packet_checked(
        db, packet_id, current_user, data_scope
    )
    with packet_errors_mapped():
        raw_token = await service.resend_invite(packet, actor_id=current_user.id)
    await db.commit()
    await queue_invite(
        db, packet=packet, raw_access_token=raw_token, suppress_if_exists=False
    )
    packet = await service.get_packet(packet_id)
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


async def _assert_owner_or_admin(db, packet, data_scope: DataScope) -> None:
    """Owner-or-admin gate for the sensitive-secret read (§D.4 / §F #3).

    The route already ran ``require_entity_access`` (contact access). For the
    encrypted F4-password read that is NOT enough: only an admin/manager
    (``can_see_all``) OR the contact OWNER may decrypt. A shared-list reader is
    refused.
    """
    if data_scope.can_see_all():
        return
    from src.contacts.models import Contact

    owner_id = (
        await db.execute(
            select(Contact.owner_id).where(Contact.id == packet.contact_id)
        )
    ).scalar_one_or_none()
    if owner_id is None or owner_id != data_scope.user_id:
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN,
            detail="Only the contact owner or an admin may read these values.",
        )


@router.get(
    "/packets/{packet_id}/documents/{doc_id}/secrets",
    response_model=SecretValuesResponse,
)
async def get_document_secrets(
    packet_id: int,
    doc_id: int,
    current_user: ReadUser,
    db: DBSession,
    data_scope: Scope,
):
    """Decrypt + return a document's sensitive answers (owner/admin only, §F #1).

    F4 passwords are stored as Fernet ciphertext (``onboarding_secret_values``)
    and NEVER rendered into the summary PDF or the public GET. This is the ONLY
    read path back to the plaintext — gated owner-or-admin, decrypting via
    ``crypto.decrypt_field``. A missing ``ONBOARDING_FIELD_KEY`` (or a token
    encrypted under a rotated-out key) fails loudly (503) rather than returning
    garbage.
    """
    service, packet = await _load_packet_checked(
        db, packet_id, current_user, data_scope
    )
    await _assert_owner_or_admin(db, packet, data_scope)

    doc = (
        await db.execute(
            select(OnboardingPacketDocument)
            .where(OnboardingPacketDocument.id == doc_id)
            .where(OnboardingPacketDocument.packet_id == packet_id)
        )
    ).scalar_one_or_none()
    if doc is None:
        raise_not_found("Onboarding document", doc_id)

    labels = {
        f.get("id"): f.get("label")
        for f in (doc.field_definitions or [])
        if f.get("id")
    }
    rows = (
        await db.execute(
            select(OnboardingSecretValue)
            .where(OnboardingSecretValue.packet_document_id == doc_id)
            .order_by(OnboardingSecretValue.field_id)
        )
    ).scalars().all()

    values: list[SecretValue] = []
    for row in rows:
        try:
            plaintext = crypto.decrypt_field(row.ciphertext)
        except crypto.OnboardingCryptoError as exc:
            raise HTTPException(
                status_code=HTTPStatus.SERVICE_UNAVAILABLE,
                detail="Secret decryption is unavailable.",
            ) from exc
        values.append(
            SecretValue(
                field_id=row.field_id,
                label=labels.get(row.field_id),
                value=plaintext,
            )
        )
    return SecretValuesResponse(document_id=doc_id, values=values)
