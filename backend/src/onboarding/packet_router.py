"""Staff (authenticated) packet routes (Phase 2, §3.1).

Thin routes delegating to ``PacketService`` / ``completion``. Every route
gates on the packet's contact via ``require_entity_access`` (data-scope) so a
sales rep can't act on another owner's contact. Reads gate ``contacts.read``,
create gates ``contacts.create``, mutations gate ``contacts.update``.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select

from src.auth.models import User
from src.core.constants import HTTPStatus
from src.core.data_scope import DataScope, get_data_scope
from src.core.entity_access import require_entity_access
from src.core.http_errors import value_error_as_400
from src.core.permissions import require_permission
from src.core.router_utils import DBSession, raise_not_found
from src.email.service import assert_gmail_connected
from src.onboarding import completion, crypto
from src.onboarding.completion_notices import queue_invite
from src.onboarding.models import (
    OnboardingPacket,
    OnboardingPacketDocument,
    OnboardingPacketUpload,
    OnboardingSecretValue,
)
from src.onboarding.packet_schemas import (
    PacketCreate,
    PacketResponse,
    PurgeResult,
    RegenerateLinkRequest,
    ResendResult,
    SecretValue,
    SecretValuesResponse,
)
from src.onboarding.packet_service import PacketService, ensure_pdf_suffix
from src.onboarding.packet_view import build_packet_response
from src.onboarding.public_helpers import (
    NO_STORE_HEADERS,
    read_pdf_or_http,
    safe_content_disposition_filename,
)
from src.onboarding.validation import packet_errors_mapped

router = APIRouter(prefix="/api/onboarding", tags=["onboarding-packets"])

ReadUser = Annotated[User, Depends(require_permission("contacts", "read"))]
CreateUser = Annotated[User, Depends(require_permission("contacts", "create"))]
UpdateUser = Annotated[User, Depends(require_permission("contacts", "update"))]
Scope = Annotated[DataScope, Depends(get_data_scope)]


async def _load_packet_checked(
    db, packet_id: int, current_user: User, data_scope: DataScope
) -> tuple[PacketService, OnboardingPacket]:
    service = PacketService(db)
    packet = await service.get_packet(packet_id)
    if packet is None:
        raise_not_found("Onboarding packet", packet_id)
    await require_entity_access(
        db, "contacts", packet.contact_id, current_user, data_scope
    )
    return service, packet


async def _preflight_sender_gmail(db, sent_by_id: int | None) -> None:
    """Pre-flight the SENDER's Gmail BEFORE minting/rotating a token (F4).

    Onboarding invites send from the packet owner's connected Gmail and have no
    transactional fallback, so a Gmail-down send/resend must fail BEFORE any
    token is minted or rotated — never stranding the client with a dead link
    and no delivery. Raises ``ValueError`` (mapped to 400) the UI turns into a
    Connect-Gmail prompt; a None owner can never send, so it is refused too.
    """
    if sent_by_id is None:
        raise ValueError(
            "This packet has no owner to send the invite from. Assign an owner "
            "before emailing the onboarding link."
        )
    await assert_gmail_connected(db, sent_by_id)


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
    # F3/F4: when emailing, pre-flight the creator's Gmail BEFORE minting so a
    # Gmail-down send creates no packet/token (nothing minted, nothing to roll
    # back). The creator is the sender (created_by_id below).
    if data.send_email:
        with value_error_as_400():
            await _preflight_sender_gmail(db, current_user.id)
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
    if data.send_email:
        # Commit the token BEFORE queuing the invite — queue_email may send
        # synchronously, so the link must be durable first (mirrors the resend
        # route + trigger.py). queue_invite is fail-soft: a send failure becomes
        # a visible failed EmailQueue row, and the live link already exists.
        await db.commit()
        await queue_invite(db, packet=packet, raw_access_token=raw_token)
    # ``access_url`` (raw token) is returned on BOTH paths so "copy link" stays
    # available as the secondary action even after an email send.
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
    # Detail view: include the client-uploaded files (D5).
    return await build_packet_response(db, service, packet, with_uploads=True)


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
    service, packet = await _load_packet_checked(
        db, packet_id, current_user, data_scope
    )
    # F4: pre-flight the OWNER's Gmail BEFORE rotating — a Gmail-down resend must
    # not kill the live link without delivering the new one (resend always
    # rotates + emails). The owner (created_by_id) is the sender.
    with value_error_as_400():
        await _preflight_sender_gmail(db, packet.created_by_id)
    with packet_errors_mapped():
        raw_token = await service.resend_invite(packet, actor_id=current_user.id)
    await db.commit()
    await queue_invite(
        db, packet=packet, raw_access_token=raw_token, suppress_if_exists=False
    )
    packet = await service.get_packet(packet_id)
    return await build_packet_response(db, service, packet)


@router.post("/packets/{packet_id}/regenerate-link", response_model=PacketResponse)
async def regenerate_link(
    packet_id: int,
    data: RegenerateLinkRequest,
    current_user: UpdateUser,
    db: DBSession,
    data_scope: Scope,
):
    """Rotate the access token + return the NEW raw ``access_url`` to copy (F5/D1).

    Recovers a lost/forgotten link without re-serving the unrecoverable old
    token (only its hash is stored): rotate (the previously shared link dies),
    commit, and return the fresh raw link. ``send_email`` optionally also
    re-queues the invite — only then is the owner's Gmail pre-flighted, since
    copying the link in-hand strands nobody. Allowed for
    active/opened/in_progress/expired; 409 for terminal states.
    """
    service, packet = await _load_packet_checked(
        db, packet_id, current_user, data_scope
    )
    if data.send_email:
        with value_error_as_400():
            await _preflight_sender_gmail(db, packet.created_by_id)
    with packet_errors_mapped():
        raw_token = await service.resend_invite(packet, actor_id=current_user.id)
    # Commit the rotated token BEFORE returning the link / queuing: a failing
    # trailing request-commit could otherwise roll the hash back to the
    # already-dead old value, leaving the recipient a broken link.
    await db.commit()
    if data.send_email:
        await queue_invite(
            db, packet=packet, raw_access_token=raw_token, suppress_if_exists=False
        )
    packet = await service.get_packet(packet_id)
    # raw_token surfaces the new link ONCE as ``access_url`` (the copy target).
    return await build_packet_response(db, service, packet, raw_token=raw_token)


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


def _inline_attachment_response(
    content: bytes, *, media_type: str, filename: str
) -> Response:
    """Proxy attachment bytes inline (no-store, nosniff) for a staff preview.

    A counterpart to the forced-download attachments route: staff want to view
    onboarding deliverables in a browser tab. ``nosniff`` pins the declared
    type; the bytes are an app-generated PDF or an upload that passed the
    allow-list + magic-byte sniff, so inline rendering carries no stored-XSS
    surface.
    """
    return Response(
        content=content,
        media_type=media_type,
        headers={
            **NO_STORE_HEADERS,
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": f'inline; filename="{filename}"',
        },
    )


@router.get("/packets/{packet_id}/uploads/{upload_id}/view", response_model=None)
async def view_packet_upload(
    packet_id: int,
    upload_id: int,
    current_user: ReadUser,
    db: DBSession,
    data_scope: Scope,
):
    """Stream one client-uploaded file inline (staff preview, contact-access).

    Scoped to this packet's documents so a guessed id can't read another
    packet's file. A ``sensitive`` upload (gov-ID etc.) is owner/admin-only —
    the same bar the generic attachments download enforces (§D.4).
    """
    service, packet = await _load_packet_checked(
        db, packet_id, current_user, data_scope
    )
    upload = (
        await db.execute(
            select(OnboardingPacketUpload)
            .join(
                OnboardingPacketDocument,
                OnboardingPacketUpload.packet_document_id
                == OnboardingPacketDocument.id,
            )
            .where(OnboardingPacketUpload.id == upload_id)
            .where(OnboardingPacketDocument.packet_id == packet_id)
        )
    ).scalar_one_or_none()
    if upload is None or upload.attachment_id is None:
        raise_not_found("Uploaded file", upload_id)
    if upload.sensitive:
        await _assert_owner_or_admin(db, packet, data_scope)

    from src.attachments.service import AttachmentService

    attachment = await AttachmentService(db).get_attachment(upload.attachment_id)
    if attachment is None:
        raise_not_found("Uploaded file", upload_id)
    content = await read_pdf_or_http(attachment.file_path)
    return _inline_attachment_response(
        content,
        media_type=upload.mime_type,
        filename=safe_content_disposition_filename(upload.original_filename),
    )


@router.get("/packets/{packet_id}/documents/{doc_id}/view", response_model=None)
async def view_packet_document(
    packet_id: int,
    doc_id: int,
    current_user: ReadUser,
    db: DBSession,
    data_scope: Scope,
):
    """Stream a completed document's generated PDF inline (staff preview).

    This is how staff see "what the client entered" — the filled/signed PDF the
    completion run landed on the document's ``attachment_id``. A document with no
    attachment yet (not completed) → 404. Contact-access gated.
    """
    service, packet = await _load_packet_checked(
        db, packet_id, current_user, data_scope
    )
    doc = (
        await db.execute(
            select(OnboardingPacketDocument)
            .where(OnboardingPacketDocument.id == doc_id)
            .where(OnboardingPacketDocument.packet_id == packet_id)
        )
    ).scalar_one_or_none()
    if doc is None or doc.attachment_id is None:
        raise_not_found("Onboarding document", doc_id)

    from src.attachments.service import AttachmentService

    attachment = await AttachmentService(db).get_attachment(doc.attachment_id)
    if attachment is None:
        raise_not_found("Onboarding document", doc_id)
    content = await read_pdf_or_http(attachment.file_path)
    return _inline_attachment_response(
        content,
        media_type="application/pdf",
        filename=safe_content_disposition_filename(
            ensure_pdf_suffix(doc.original_filename)
        ),
    )
