"""Proposal API routes."""

import base64
import binascii
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse, Response
from sqlalchemy import select

from src.attachments.models import Attachment
from src.attachments.schemas import AttachmentListResponse, AttachmentResponse
from src.attachments.service import AttachmentService
from src.audit.utils import (
    audit_entity_create,
    audit_entity_delete,
    audit_entity_update,
    snapshot_entity,
)
from src.core.client_ip import get_client_ip
from src.core.constants import ENTITY_TYPE_PROPOSALS, EntityNames, HTTPStatus
from src.core.data_scope import DataScope, check_record_access_or_shared, get_data_scope
from src.core.http_errors import value_error_as_400
from src.core.rate_limit import limiter
from src.core.router_utils import (
    CurrentUser,
    DBSession,
    calculate_pages,
    check_ownership,
    get_entity_or_404,
    raise_bad_request,
    raise_not_found,
)
from src.events.service import PROPOSAL_ACCEPTED, PROPOSAL_REJECTED, PROPOSAL_SENT, emit
from src.proposals.attachment_views import (
    ProposalAttachmentView,
    _hash_token,
    record_attachment_view,
)
from src.proposals.schemas import (
    CreateFromTemplateRequest,
    ProposalAcceptRequest,
    ProposalAttachmentPublicItem,
    ProposalBranding,
    ProposalCreate,
    ProposalListResponse,
    ProposalPublicResponse,
    ProposalRejectRequest,
    ProposalResponse,
    ProposalSendRequest,
    ProposalSigningDocumentResponse,
    ProposalSigningDocumentUpdate,
    ProposalTemplateCreate,
    ProposalTemplateResponse,
    ProposalTemplateUpdate,
    ProposalUpdate,
)
from src.proposals.service import ProposalService, ProposalTemplateService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/proposals", tags=["proposals"])

# Hard cap on the raw signature_image payload (base64-encoded PNG)
# accepted by /public/{token}/accept. A typical drawn signature lands
# at ~5–30 KB; the cap keeps a hostile client from posting a multi-MB
# payload that would force the row into TOAST storage and bloat the
# audit page render.
_MAX_SIGNATURE_BYTES = 200_000


def _decode_signature_image(payload: str) -> bytes:
    """Decode the base64 PNG submitted from the signing modal.

    Accepts both bare base64 and ``data:image/png;base64,...`` URLs.
    Raises ``HTTPException(400)`` on invalid payloads so the modal
    can surface a clean error.
    """
    raw = payload.strip()
    if raw.startswith("data:"):
        comma = raw.find(",")
        if comma == -1:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail="signature_image must be a base64 PNG",
            )
        raw = raw[comma + 1 :]
    try:
        decoded = base64.b64decode(raw, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="signature_image is not valid base64",
        ) from exc
    if len(decoded) > _MAX_SIGNATURE_BYTES:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="signature_image exceeds 200 KB limit",
        )
    if not decoded.startswith(b"\x89PNG\r\n\x1a\n"):
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="signature_image must be a PNG",
        )
    return decoded


@router.get("", response_model=ProposalListResponse)
async def list_proposals(
    current_user: CurrentUser,
    db: DBSession,
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = None,
    status: str | None = None,
    contact_id: int | None = None,
    company_id: int | None = None,
    opportunity_id: int | None = None,
    quote_id: int | None = None,
    owner_id: int | None = None,
    order_by: str | None = None,
    order_dir: str | None = None,
):
    """List proposals with pagination and filters."""
    effective_owner_id = owner_id if data_scope.can_see_all() else data_scope.owner_id

    service = ProposalService(db)

    proposals, total = await service.get_list(
        page=page,
        page_size=page_size,
        search=search,
        status=status,
        contact_id=contact_id,
        company_id=company_id,
        opportunity_id=opportunity_id,
        quote_id=quote_id,
        owner_id=effective_owner_id,
        shared_entity_ids=data_scope.get_shared_ids(ENTITY_TYPE_PROPOSALS),
        order_by=order_by,
        order_dir=order_dir,
    )

    return ProposalListResponse(
        items=[ProposalResponse.model_validate(p) for p in proposals],
        total=total,
        page=page,
        page_size=page_size,
        pages=calculate_pages(total, page_size),
    )


@router.post("", response_model=ProposalResponse, status_code=HTTPStatus.CREATED)
async def create_proposal(
    proposal_data: ProposalCreate,
    request: Request,
    current_user: CurrentUser,
    db: DBSession,
):
    """Create a new proposal."""
    service = ProposalService(db)
    with value_error_as_400():
        proposal = await service.create(proposal_data, current_user.id)

    ip_address = get_client_ip(request)
    await audit_entity_create(db, "proposal", proposal.id, current_user.id, ip_address)

    return ProposalResponse.model_validate(proposal)


@router.get("/templates", response_model=list[ProposalTemplateResponse])
async def list_templates(
    current_user: CurrentUser,
    db: DBSession,
    category: str | None = None,
):
    """List all proposal templates, optionally filtered by category."""
    service = ProposalTemplateService(db)
    templates = await service.get_list(category=category)
    return [ProposalTemplateResponse.model_validate(t) for t in templates]


@router.post("/templates", response_model=ProposalTemplateResponse, status_code=HTTPStatus.CREATED)
async def create_template(
    template_data: ProposalTemplateCreate,
    current_user: CurrentUser,
    db: DBSession,
):
    """Create a new proposal template."""
    from src.proposals.models import ProposalTemplate

    template = ProposalTemplate(
        name=template_data.name,
        description=template_data.description,
        body=template_data.body,
        legal_terms=template_data.legal_terms,
        category=template_data.category,
        is_default=template_data.is_default,
        owner_id=current_user.id,
        created_by_id=current_user.id,
    )
    db.add(template)
    await db.flush()
    await db.refresh(template)
    return ProposalTemplateResponse.model_validate(template)


@router.get("/templates/{template_id}", response_model=ProposalTemplateResponse)
async def get_template(
    template_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Get a proposal template by ID."""
    service = ProposalTemplateService(db)
    template = await service.get_by_id(template_id)
    if not template:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Template not found")
    return ProposalTemplateResponse.model_validate(template)


@router.patch("/templates/{template_id}", response_model=ProposalTemplateResponse)
async def update_template(
    template_id: int,
    template_data: ProposalTemplateUpdate,
    current_user: CurrentUser,
    db: DBSession,
):
    """Update a proposal template."""
    service = ProposalTemplateService(db)
    template = await service.get_by_id(template_id)
    if not template:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Template not found")

    update_data = template_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(template, field, value)

    await db.flush()
    await db.refresh(template)
    return ProposalTemplateResponse.model_validate(template)


@router.delete("/templates/{template_id}", status_code=HTTPStatus.NO_CONTENT)
async def delete_template(
    template_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Delete a proposal template."""
    service = ProposalTemplateService(db)
    template = await service.get_by_id(template_id)
    if not template:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Template not found")
    await db.delete(template)
    await db.flush()


@router.post("/from-template", response_model=ProposalResponse, status_code=HTTPStatus.CREATED)
async def create_proposal_from_template(
    request_data: CreateFromTemplateRequest,
    request: Request,
    current_user: CurrentUser,
    db: DBSession,
):
    """Create a new proposal from a template with merge variable replacement."""
    service = ProposalService(db)
    template_service = ProposalTemplateService(db)

    template = await template_service.get_by_id(request_data.template_id)
    if not template:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Template not found")

    # Fetch contact
    from sqlalchemy import select

    from src.contacts.models import Contact
    contact_result = await db.execute(
        select(Contact).where(Contact.id == request_data.contact_id)
    )
    contact = contact_result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Contact not found")

    # Fetch company if provided
    company = None
    if request_data.company_id:
        from src.companies.models import Company
        company_result = await db.execute(
            select(Company).where(Company.id == request_data.company_id)
        )
        company = company_result.scalar_one_or_none()
        if not company:
            raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Company not found")

    # Build merge variables
    from datetime import date
    contact_name = f"{contact.first_name} {contact.last_name}"
    company_name = company.name if company else ""
    company_address_parts = []
    if company:
        for part in [company.address_line1, company.address_line2, company.city, company.state, company.postal_code, company.country]:
            if part:
                company_address_parts.append(part)
    company_address = ", ".join(company_address_parts)

    variables = {
        "contact_name": contact_name,
        "company_name": company_name,
        "date": date.today().strftime("%B %d, %Y"),
        "contact_email": contact.email or "",
        "contact_phone": contact.phone or "",
        "company_address": company_address,
    }

    # Merge custom variables
    if request_data.custom_variables:
        variables.update(request_data.custom_variables)

    # Replace variables in body and legal_terms
    filled_body = await service.substitute_template_variables(template.body, variables)
    filled_legal_terms = None
    if template.legal_terms:
        filled_legal_terms = await service.substitute_template_variables(template.legal_terms, variables)

    # Create proposal
    proposal_data = ProposalCreate(
        title=template.name,
        content=filled_body,
        terms=filled_legal_terms,
        contact_id=request_data.contact_id,
        company_id=request_data.company_id,
        status="draft",
    )
    with value_error_as_400():
        proposal = await service.create(proposal_data, current_user.id)

    ip_address = get_client_ip(request)
    await audit_entity_create(db, "proposal", proposal.id, current_user.id, ip_address)

    return ProposalResponse.model_validate(proposal)


def _ensure_unsigned(proposal) -> None:
    """Refuse staff attachment mutations once the customer has signed.

    The signed PDF mailed to the client lists exactly the attachments
    that existed at sign time; mutating the set after that point would
    silently desync the on-record bundle from what the signer agreed to.
    """
    if proposal.signed_at is not None:
        raise_bad_request(
            "Cannot modify attachments on a signed proposal — clone it instead",
        )


def _proposal_attachment_or_404(
    attachment: Attachment | None, proposal_id: int,
) -> None:
    if (
        attachment is None
        or attachment.entity_type != "proposals"
        or attachment.entity_id != proposal_id
    ):
        raise_not_found("Attachment")


async def _signing_document_or_404(
    service: ProposalService,
    proposal_id: int,
    document_id: int,
):
    document = await service.get_signing_document(proposal_id, document_id)
    if document is None:
        raise_not_found("Signing document")
    return document


@router.post(
    "/{proposal_id}/attachments",
    response_model=AttachmentResponse,
    status_code=HTTPStatus.CREATED,
)
async def upload_proposal_attachment(
    proposal_id: int,
    current_user: CurrentUser,
    db: DBSession,
    file: UploadFile = File(...),
):
    """Staff upload of a PDF attachment for a proposal.

    PDF only — non-PDF uploads 400 because the public viewer renders
    these inline as PDFs. Refuses once the proposal is signed so the
    bundle the signer agreed to stays immutable.
    """
    service = ProposalService(db)
    proposal = await get_entity_or_404(service, proposal_id, EntityNames.PROPOSAL)
    check_ownership(proposal, current_user, EntityNames.PROPOSAL)
    _ensure_unsigned(proposal)

    filename = (file.filename or "").lower()
    content_type = (file.content_type or "").lower()
    if not (filename.endswith(".pdf") or content_type == "application/pdf"):
        raise_bad_request("Only PDF attachments are allowed on proposals")

    att_service = AttachmentService(db)
    try:
        attachment = await att_service.upload_file(
            file=file,
            entity_type="proposals",
            entity_id=proposal_id,
            user_id=current_user.id,
            category="document",
        )
    except ValueError as exc:
        raise_bad_request(str(exc))

    return AttachmentResponse.model_validate(attachment)


@router.get(
    "/{proposal_id}/attachments",
    response_model=AttachmentListResponse,
)
async def list_proposal_attachments(
    proposal_id: int,
    current_user: CurrentUser,
    db: DBSession,
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
):
    """Staff list of attachments for a proposal."""
    service = ProposalService(db)
    proposal = await get_entity_or_404(service, proposal_id, EntityNames.PROPOSAL)
    check_record_access_or_shared(
        proposal, current_user, data_scope.role_name,
        shared_entity_ids=data_scope.get_shared_ids(ENTITY_TYPE_PROPOSALS),
    )

    att_service = AttachmentService(db)
    items, total = await att_service.list_attachments("proposals", proposal_id)
    return AttachmentListResponse(
        items=[AttachmentResponse.model_validate(a) for a in items],
        total=total,
    )


@router.delete(
    "/{proposal_id}/attachments/{attachment_id}",
    status_code=HTTPStatus.NO_CONTENT,
)
async def delete_proposal_attachment(
    proposal_id: int,
    attachment_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Staff delete of a proposal attachment. Refuses once signed."""
    service = ProposalService(db)
    proposal = await get_entity_or_404(service, proposal_id, EntityNames.PROPOSAL)
    check_ownership(proposal, current_user, EntityNames.PROPOSAL)
    _ensure_unsigned(proposal)

    att_service = AttachmentService(db)
    attachment = await att_service.get_attachment(attachment_id)
    _proposal_attachment_or_404(attachment, proposal_id)

    await att_service.delete_attachment(attachment)


@router.get("/public/{token}/attachments")
@limiter.limit("30/minute")
async def list_public_proposal_attachments(
    token: str,
    request: Request,
    db: DBSession,
) -> list[ProposalAttachmentPublicItem]:
    """Public list of attachments for a proposal token, with per-token viewed flag."""
    import hmac as _hmac

    service = ProposalService(db)
    proposal = await service.get_public_proposal(token)
    if not proposal or not _hmac.compare_digest(proposal.public_token or "", token):
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Proposal not found")

    att_service = AttachmentService(db)
    items, _total = await att_service.list_attachments("proposals", proposal.id)
    if not items:
        return []

    token_hash = _hash_token(token)
    viewed_rows = await db.execute(
        select(ProposalAttachmentView.attachment_id)
        .where(ProposalAttachmentView.token_hash == token_hash)
        .where(ProposalAttachmentView.attachment_id.in_([a.id for a in items]))
    )
    viewed_ids = {r[0] for r in viewed_rows.all()}

    return [
        ProposalAttachmentPublicItem(
            id=a.id,
            filename=a.original_filename,
            file_size=a.file_size,
            mime_type=a.mime_type,
            viewed=a.id in viewed_ids,
        )
        for a in items
    ]


@router.get("/public/{token}/attachments/{attachment_id}/download")
@limiter.limit("30/minute")
async def download_public_proposal_attachment(
    token: str,
    attachment_id: int,
    request: Request,
    db: DBSession,
):
    """Public download of a proposal attachment.

    Records the per-token view for audit purposes and redirects to a
    short-lived R2 presigned URL. Falls back to a direct file response
    when object storage isn't configured (dev/test). The view rows no
    longer gate signing — the Sign-to-Confirm modal's T&C card
    replaced the forced PDF-open step on 2026-05-14.
    """
    import hmac as _hmac

    service = ProposalService(db)
    proposal = await service.get_public_proposal(token)
    if not proposal or not _hmac.compare_digest(proposal.public_token or "", token):
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Proposal not found")

    att_service = AttachmentService(db)
    attachment = await att_service.get_attachment(attachment_id)
    if (
        attachment is None
        or attachment.entity_type != "proposals"
        or attachment.entity_id != proposal.id
    ):
        # Same 404 as a missing attachment so cross-tenant probes can't
        # distinguish "exists but not yours" from "doesn't exist".
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Attachment not found")

    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    await record_attachment_view(
        db,
        attachment_id=attachment.id,
        token=token,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    try:
        download_url = await att_service.get_download_url(attachment)
    except Exception as exc:
        logger.info("R2 presign failed for attachment %s: %s", attachment.id, exc)
        download_url = None

    if download_url:
        return RedirectResponse(url=download_url, status_code=307)

    file_path = att_service.get_file_path(attachment)
    if not file_path or not file_path.exists():
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="File not found")

    return FileResponse(
        path=str(file_path),
        filename=attachment.original_filename,
        media_type=attachment.mime_type,
    )


@router.get("/public/{token}", response_model=ProposalPublicResponse)
@limiter.limit("60/minute")
async def get_public_proposal(
    token: str,
    request: Request,
    db: DBSession,
):
    """Public view of a proposal (no auth required). Increments view count.

    Keyed on Proposal.public_token instead of proposal_number — the old
    numeric identifier was enumerable.
    """
    import hmac as _hmac

    service = ProposalService(db)
    proposal = await service.get_public_proposal(token)
    if not proposal or not _hmac.compare_digest(proposal.public_token or "", token):
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Proposal not found")

    # Record the view
    ip_address = get_client_ip(request)
    user_agent = request.headers.get("user-agent")
    await service.record_view(proposal.id, ip_address, user_agent)

    # Resolve branding from proposal owner's tenant
    branding_data = await service.get_branding_for_proposal(proposal)
    branding = ProposalBranding(
        company_name=branding_data.get("company_name"),
        logo_url=branding_data.get("logo_url"),
        primary_color=branding_data.get("primary_color", "#6366f1"),
        secondary_color=branding_data.get("secondary_color", "#8b5cf6"),
        accent_color=branding_data.get("accent_color", "#22c55e"),
        bg_color_light=branding_data.get("bg_color_light", "#f9fafb"),
        surface_color_light=branding_data.get("surface_color_light", "#ffffff"),
        footer_text=branding_data.get("footer_text"),
        privacy_policy_url=branding_data.get("privacy_policy_url"),
        terms_of_service_url=branding_data.get("terms_of_service_url"),
    )

    response = ProposalPublicResponse.model_validate(proposal)
    response.branding = branding
    response.terms_and_conditions = await service.get_effective_terms_and_conditions(
        proposal,
    )
    response.designated_signer_email = (
        proposal.designated_signer_email
        or (proposal.contact.email if proposal.contact else None)
    )
    signing_document_count = len(proposal.signing_documents or [])
    response.signing_document_count = signing_document_count
    response.has_master_contract = bool(
        proposal.master_contract_pdf_path or signing_document_count
    )

    # Per-token attachment list — surfaced for review only; opening
    # everything is no longer a precondition to signing.
    att_service = AttachmentService(db)
    items, _total = await att_service.list_attachments("proposals", proposal.id)
    if items:
        token_hash = _hash_token(token)
        viewed_rows = await db.execute(
            select(ProposalAttachmentView.attachment_id)
            .where(ProposalAttachmentView.token_hash == token_hash)
            .where(ProposalAttachmentView.attachment_id.in_([a.id for a in items]))
        )
        viewed_ids = {r[0] for r in viewed_rows.all()}
        response.attachments = [
            ProposalAttachmentPublicItem(
                id=a.id,
                filename=a.original_filename,
                file_size=a.file_size,
                mime_type=a.mime_type,
                viewed=a.id in viewed_ids,
            )
            for a in items
        ]
    return response


@router.post("/public/{token}/accept", response_model=ProposalPublicResponse)
@limiter.limit("10/minute")
async def accept_proposal_public(
    token: str,
    accept_data: ProposalAcceptRequest,
    request: Request,
    db: DBSession,
):
    """Accept a proposal via the public Sign-to-Confirm modal.

    Captures the drawn signature image + ESIGN consent + signer
    name/email/IP/user-agent and transitions the proposal to
    ``accepted``. Rejects submissions whose signer_email does not
    match the proposal's ``designated_signer_email`` (or, failing
    that, the linked contact's email). When a master contract PDF is
    on file, stamps the signature onto a copy and persists the
    composite to R2. No Stripe spawn — billing is created manually
    via the Payments module per the 2026-05-14 product decision.
    """
    import hmac as _hmac

    service = ProposalService(db)
    proposal = await service.get_public_proposal(token)
    if not proposal or not _hmac.compare_digest(proposal.public_token or "", token):
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Proposal not found")

    signer_ip = get_client_ip(request)
    signer_user_agent = request.headers.get("user-agent")
    signature_bytes = _decode_signature_image(accept_data.signature_image)
    with value_error_as_400():
        proposal = await service.accept_proposal_public(
            proposal,
            signer_name=accept_data.signer_name,
            signer_email=accept_data.signer_email,
            signature_image=signature_bytes,
            agreed_to_terms=accept_data.agreed_to_terms,
            signer_ip=signer_ip,
            signer_user_agent=signer_user_agent,
        )

    # proposal_signed notification + email is dispatched by ProposalService.accept_proposal_public
    # via notify_on_proposal_signed (matrix-gated). Don't double-fire from the router.

    branding_data = await service.get_branding_for_proposal(proposal)
    response = ProposalPublicResponse.model_validate(proposal)
    response.branding = ProposalBranding(
        company_name=branding_data.get("company_name"),
        logo_url=branding_data.get("logo_url"),
        primary_color=branding_data.get("primary_color", "#6366f1"),
        secondary_color=branding_data.get("secondary_color", "#8b5cf6"),
        accent_color=branding_data.get("accent_color", "#22c55e"),
        bg_color_light=branding_data.get("bg_color_light", "#f9fafb"),
        surface_color_light=branding_data.get("surface_color_light", "#ffffff"),
        footer_text=branding_data.get("footer_text"),
        privacy_policy_url=branding_data.get("privacy_policy_url"),
        terms_of_service_url=branding_data.get("terms_of_service_url"),
    )
    response.terms_and_conditions = await service.get_effective_terms_and_conditions(
        proposal,
    )
    response.designated_signer_email = (
        proposal.designated_signer_email
        or (proposal.contact.email if proposal.contact else None)
    )
    signing_document_count = len(proposal.signing_documents or [])
    response.signing_document_count = signing_document_count
    response.has_master_contract = bool(
        proposal.master_contract_pdf_path or signing_document_count
    )
    return response


@router.post("/public/{token}/reject", response_model=ProposalPublicResponse)
@limiter.limit("10/minute")
async def reject_proposal_public(
    token: str,
    reject_data: ProposalRejectRequest,
    request: Request,
    db: DBSession,
):
    """Reject a proposal via public link (no auth required).

    Requires signer_email to match the designated/contact email on the
    proposal — otherwise anyone who received a forwarded link could
    permanently reject.
    """
    import hmac as _hmac

    service = ProposalService(db)
    proposal = await service.get_public_proposal(token)
    if not proposal or not _hmac.compare_digest(proposal.public_token or "", token):
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Proposal not found")

    signer_ip = get_client_ip(request)
    signer_user_agent = request.headers.get("user-agent")
    with value_error_as_400():
        proposal = await service.reject_proposal_public(
            proposal,
            reason=reject_data.reason,
            signer_ip=signer_ip,
            signer_user_agent=signer_user_agent,
            signer_email=reject_data.signer_email,
        )

    # Public reject is the customer-facing path — owner needs the ping.
    # user_id=None because the actor is unauthenticated; the handler
    # resolves the recipient via the proposal's owner_id.
    await emit(PROPOSAL_REJECTED, {
        "entity_id": proposal.id,
        "entity_type": "proposal",
        "user_id": None,
        "data": {
            "proposal_number": proposal.proposal_number,
            "status": proposal.status,
            "rejected_via": "public",
            "reason": reject_data.reason,
        },
    })

    branding_data = await service.get_branding_for_proposal(proposal)
    response = ProposalPublicResponse.model_validate(proposal)
    response.branding = ProposalBranding(
        company_name=branding_data.get("company_name"),
        logo_url=branding_data.get("logo_url"),
        primary_color=branding_data.get("primary_color", "#6366f1"),
        secondary_color=branding_data.get("secondary_color", "#8b5cf6"),
        accent_color=branding_data.get("accent_color", "#22c55e"),
        bg_color_light=branding_data.get("bg_color_light", "#f9fafb"),
        surface_color_light=branding_data.get("surface_color_light", "#ffffff"),
        footer_text=branding_data.get("footer_text"),
        privacy_policy_url=branding_data.get("privacy_policy_url"),
        terms_of_service_url=branding_data.get("terms_of_service_url"),
    )
    return response


@router.get(
    "/{proposal_id}/signing-documents",
    response_model=list[ProposalSigningDocumentResponse],
)
async def list_signing_documents(
    proposal_id: int,
    current_user: CurrentUser,
    db: DBSession,
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
):
    """List PDFs on this proposal that need explicit signature placement."""
    service = ProposalService(db)
    proposal = await get_entity_or_404(service, proposal_id, EntityNames.PROPOSAL)
    check_record_access_or_shared(
        proposal, current_user, data_scope.role_name,
        shared_entity_ids=data_scope.get_shared_ids(ENTITY_TYPE_PROPOSALS),
    )
    return [
        ProposalSigningDocumentResponse.model_validate(doc)
        for doc in await service.list_signing_documents(proposal_id)
    ]


@router.post(
    "/{proposal_id}/signing-documents",
    response_model=ProposalSigningDocumentResponse,
    status_code=HTTPStatus.CREATED,
)
async def upload_signing_document(
    proposal_id: int,
    current_user: CurrentUser,
    db: DBSession,
    file: UploadFile = File(...),
):
    """Upload one signable PDF. Every uploaded PDF needs a box before send."""
    service = ProposalService(db)
    proposal = await get_entity_or_404(service, proposal_id, EntityNames.PROPOSAL)
    check_ownership(proposal, current_user, EntityNames.PROPOSAL)
    _ensure_unsigned(proposal)
    content = await file.read()
    with value_error_as_400():
        document = await service.upload_signing_document_pdf(
            proposal,
            content=content,
            filename=file.filename,
            user_id=current_user.id,
        )
    return ProposalSigningDocumentResponse.model_validate(document)


@router.patch(
    "/{proposal_id}/signing-documents/{document_id}",
    response_model=ProposalSigningDocumentResponse,
)
async def update_signing_document(
    proposal_id: int,
    document_id: int,
    document_data: ProposalSigningDocumentUpdate,
    current_user: CurrentUser,
    db: DBSession,
):
    """Save or clear the visual signature area for one signable PDF."""
    service = ProposalService(db)
    proposal = await get_entity_or_404(service, proposal_id, EntityNames.PROPOSAL)
    check_ownership(proposal, current_user, EntityNames.PROPOSAL)
    _ensure_unsigned(proposal)
    document = await _signing_document_or_404(service, proposal_id, document_id)
    with value_error_as_400():
        document = await service.update_signing_document(
            proposal,
            document,
            signature_field_coords=document_data.signature_field_coords,
            user_id=current_user.id,
        )
    return ProposalSigningDocumentResponse.model_validate(document)


@router.delete(
    "/{proposal_id}/signing-documents/{document_id}",
    status_code=HTTPStatus.NO_CONTENT,
)
async def delete_signing_document(
    proposal_id: int,
    document_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Delete a signable PDF before the proposal is signed."""
    service = ProposalService(db)
    proposal = await get_entity_or_404(service, proposal_id, EntityNames.PROPOSAL)
    check_ownership(proposal, current_user, EntityNames.PROPOSAL)
    _ensure_unsigned(proposal)
    document = await _signing_document_or_404(service, proposal_id, document_id)
    with value_error_as_400():
        await service.delete_signing_document(proposal, document)


@router.get("/{proposal_id}/signing-documents/{document_id}/pdf")
@limiter.limit("30/minute")
async def download_signing_document_pdf(
    proposal_id: int,
    document_id: int,
    request: Request,
    current_user: CurrentUser,
    db: DBSession,
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
):
    """Stream the source PDF for placement preview."""
    from botocore.exceptions import ClientError

    from src.attachments.object_storage import download_object_bytes

    service = ProposalService(db)
    proposal = await get_entity_or_404(service, proposal_id, EntityNames.PROPOSAL)
    check_record_access_or_shared(
        proposal, current_user, data_scope.role_name,
        shared_entity_ids=data_scope.get_shared_ids(ENTITY_TYPE_PROPOSALS),
    )
    document = await _signing_document_or_404(service, proposal_id, document_id)
    try:
        content = await download_object_bytes(document.pdf_path)
    except ClientError as exc:
        response = getattr(exc, "response", None) or {}
        err = response.get("Error", {}) if isinstance(response, dict) else {}
        code = err.get("Code", "")
        if code in ("NoSuchKey", "404", "NotFound"):
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail="Signing document file missing from storage",
            ) from exc
        logger.exception(
            "R2 ClientError fetching signing document %s for proposal %s",
            document_id, proposal_id,
        )
        raise HTTPException(
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            detail="File storage temporarily unavailable — try again later",
        ) from exc
    except Exception as exc:
        logger.exception(
            "Unexpected error fetching signing document %s for proposal %s",
            document_id, proposal_id,
        )
        raise HTTPException(
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            detail="File storage temporarily unavailable — try again later",
        ) from exc
    return Response(content=content, media_type="application/pdf")


@router.get("/{proposal_id}/signing-documents/{document_id}/signed-pdf")
@limiter.limit("30/minute")
async def download_signing_document_signed_pdf(
    proposal_id: int,
    document_id: int,
    request: Request,
    current_user: CurrentUser,
    db: DBSession,
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
):
    """Stream one signed copy PDF after the public signer accepts."""
    from botocore.exceptions import ClientError

    from src.attachments.object_storage import download_object_bytes

    service = ProposalService(db)
    proposal = await get_entity_or_404(service, proposal_id, EntityNames.PROPOSAL)
    check_record_access_or_shared(
        proposal, current_user, data_scope.role_name,
        shared_entity_ids=data_scope.get_shared_ids(ENTITY_TYPE_PROPOSALS),
    )
    document = await _signing_document_or_404(service, proposal_id, document_id)
    if not document.signed_pdf_path:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail="No signed PDF on file for this document",
        )
    try:
        content = await download_object_bytes(document.signed_pdf_path)
    except ClientError as exc:
        response = getattr(exc, "response", None) or {}
        err = response.get("Error", {}) if isinstance(response, dict) else {}
        code = err.get("Code", "")
        if code in ("NoSuchKey", "404", "NotFound"):
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail="Signed PDF file missing from storage — re-stamp to regenerate",
            ) from exc
        logger.exception(
            "R2 ClientError fetching signed document %s for proposal %s",
            document_id, proposal_id,
        )
        raise HTTPException(
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            detail="File storage temporarily unavailable — try again later",
        ) from exc
    except Exception as exc:
        logger.exception(
            "Unexpected error fetching signed document %s for proposal %s",
            document_id, proposal_id,
        )
        raise HTTPException(
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            detail="File storage temporarily unavailable — try again later",
        ) from exc
    return Response(content=content, media_type="application/pdf")


@router.post(
    "/{proposal_id}/master-contract",
    response_model=ProposalResponse,
)
async def upload_master_contract(
    proposal_id: int,
    current_user: CurrentUser,
    db: DBSession,
    file: UploadFile = File(...),
):
    """Upload (or replace) the master service agreement PDF.

    On signing, the customer's drawn signature is stamped onto a copy
    of this PDF + an audit page is appended. The composite is stored
    at ``proposals.signed_pdf_path``, emailed to the signer, and the
    owner receives an in-app/email ``proposal_signed`` notification
    (matrix-gated). The owner does NOT automatically receive the PDF
    attachment.
    """
    service = ProposalService(db)
    proposal = await get_entity_or_404(service, proposal_id, EntityNames.PROPOSAL)
    check_ownership(proposal, current_user, EntityNames.PROPOSAL)
    content = await file.read()
    with value_error_as_400():
        proposal = await service.upload_master_contract_pdf(
            proposal,
            content=content,
            filename=file.filename or "master.pdf",
        )
    return ProposalResponse.model_validate(proposal)


@router.get("/{proposal_id}/master-contract")
@limiter.limit("30/minute")
async def download_master_contract(
    proposal_id: int,
    request: Request,
    current_user: CurrentUser,
    db: DBSession,
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
):
    """Stream the raw master service agreement PDF bytes back to staff.

    Returned as ``application/pdf`` so the SignatureFieldPicker can hand
    the blob straight to pdf.js — going through the backend keeps the
    bearer-auth check, sidesteps R2 CORS (no headers on cross-origin
    GETs to the bucket), and avoids a redirect-follow round-trip from
    the browser.

    Failure mapping: a missing R2 object (NoSuchKey / 404) is a 404 so
    the operator gets a clear "the bytes are gone, re-upload" signal
    instead of a misleading "storage unavailable, try again later".
    Other ClientError + unexpected exceptions stay as 503 — a hint to
    check R2 config + retry once the platform is healthy.
    """
    from botocore.exceptions import ClientError

    from src.attachments.object_storage import download_object_bytes

    service = ProposalService(db)
    proposal = await get_entity_or_404(service, proposal_id, EntityNames.PROPOSAL)
    check_record_access_or_shared(
        proposal, current_user, data_scope.role_name,
        shared_entity_ids=data_scope.get_shared_ids(ENTITY_TYPE_PROPOSALS),
    )
    if not proposal.master_contract_pdf_path:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail="No master contract on file",
        )
    try:
        content = await download_object_bytes(proposal.master_contract_pdf_path)
    except ClientError as exc:
        response = getattr(exc, "response", None) or {}
        err = response.get("Error", {}) if isinstance(response, dict) else {}
        code = err.get("Code", "")
        if code in ("NoSuchKey", "404", "NotFound"):
            logger.warning(
                "Master contract object missing for proposal %s (key=%r): %s",
                proposal_id, proposal.master_contract_pdf_path, code,
            )
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail="Master contract file missing from storage",
            ) from exc
        logger.exception(
            "R2 ClientError fetching master contract for proposal %s (code=%s)",
            proposal_id, code,
        )
        raise HTTPException(
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            detail="File storage temporarily unavailable — try again later",
        ) from exc
    except Exception as exc:
        logger.exception(
            "Unexpected error fetching master contract for proposal %s",
            proposal_id,
        )
        raise HTTPException(
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            detail="File storage temporarily unavailable — try again later",
        ) from exc
    return Response(content=content, media_type="application/pdf")


@router.get("/{proposal_id}/signed-pdf")
@limiter.limit("30/minute")
async def download_signed_pdf(
    proposal_id: int,
    request: Request,
    current_user: CurrentUser,
    db: DBSession,
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
):
    """Stream the stamped signed-copy PDF bytes back to staff.

    Returns 404 when no signed PDF is on file (proposal not yet signed,
    or the accept-time stamper fail-softed without producing a copy —
    in which case the operator should hit ``/restamp`` first). Mirrors
    the master-contract endpoint's R2 failure mapping so a missing
    object surfaces a clear 404 instead of a 503.
    """
    from botocore.exceptions import ClientError

    from src.attachments.object_storage import download_object_bytes

    service = ProposalService(db)
    proposal = await get_entity_or_404(service, proposal_id, EntityNames.PROPOSAL)
    check_record_access_or_shared(
        proposal, current_user, data_scope.role_name,
        shared_entity_ids=data_scope.get_shared_ids(ENTITY_TYPE_PROPOSALS),
    )
    if not proposal.signed_pdf_path:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail="No signed PDF on file",
        )
    try:
        content = await download_object_bytes(proposal.signed_pdf_path)
    except ClientError as exc:
        response = getattr(exc, "response", None) or {}
        err = response.get("Error", {}) if isinstance(response, dict) else {}
        code = err.get("Code", "")
        if code in ("NoSuchKey", "404", "NotFound"):
            logger.warning(
                "Signed PDF object missing for proposal %s (key=%r): %s",
                proposal_id, proposal.signed_pdf_path, code,
            )
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail="Signed PDF file missing from storage — re-stamp to regenerate",
            ) from exc
        logger.exception(
            "R2 ClientError fetching signed PDF for proposal %s (code=%s)",
            proposal_id, code,
        )
        raise HTTPException(
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            detail="File storage temporarily unavailable — try again later",
        ) from exc
    except Exception as exc:
        logger.exception(
            "Unexpected error fetching signed PDF for proposal %s",
            proposal_id,
        )
        raise HTTPException(
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            detail="File storage temporarily unavailable — try again later",
        ) from exc
    return Response(content=content, media_type="application/pdf")


@router.get("/{proposal_id}", response_model=ProposalResponse)
async def get_proposal(
    proposal_id: int,
    current_user: CurrentUser,
    db: DBSession,
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
):
    """Get a proposal by ID."""
    service = ProposalService(db)
    proposal = await get_entity_or_404(service, proposal_id, EntityNames.PROPOSAL)
    check_record_access_or_shared(
        proposal, current_user, data_scope.role_name,
        shared_entity_ids=data_scope.get_shared_ids(ENTITY_TYPE_PROPOSALS),
    )
    return ProposalResponse.model_validate(proposal)


@router.patch("/{proposal_id}", response_model=ProposalResponse)
async def update_proposal(
    proposal_id: int,
    proposal_data: ProposalUpdate,
    request: Request,
    current_user: CurrentUser,
    db: DBSession,
):
    """Update a proposal."""
    service = ProposalService(db)
    proposal = await get_entity_or_404(service, proposal_id, EntityNames.PROPOSAL)
    check_ownership(proposal, current_user, EntityNames.PROPOSAL)

    update_fields = list(proposal_data.model_dump(exclude_unset=True).keys())
    old_data = snapshot_entity(proposal, update_fields)

    with value_error_as_400():
        updated_proposal = await service.update(proposal, proposal_data, current_user.id)

    new_data = snapshot_entity(updated_proposal, update_fields)
    ip_address = get_client_ip(request)
    await audit_entity_update(db, "proposal", updated_proposal.id, current_user.id, old_data, new_data, ip_address)

    return ProposalResponse.model_validate(updated_proposal)


@router.delete("/{proposal_id}", status_code=HTTPStatus.NO_CONTENT)
async def delete_proposal(
    proposal_id: int,
    request: Request,
    current_user: CurrentUser,
    db: DBSession,
):
    """Delete a proposal."""
    service = ProposalService(db)
    proposal = await get_entity_or_404(service, proposal_id, EntityNames.PROPOSAL)
    check_ownership(proposal, current_user, EntityNames.PROPOSAL)

    ip_address = get_client_ip(request)
    await audit_entity_delete(db, "proposal", proposal.id, current_user.id, ip_address)

    await service.delete(proposal)


@router.post("/{proposal_id}/send", response_model=ProposalResponse)
async def send_proposal(
    proposal_id: int,
    current_user: CurrentUser,
    db: DBSession,
    send_request: ProposalSendRequest | None = None,
):
    """Send a branded proposal email and mark as sent."""
    service = ProposalService(db)
    proposal = await get_entity_or_404(service, proposal_id, EntityNames.PROPOSAL)
    check_ownership(proposal, current_user, EntityNames.PROPOSAL)
    attach_pdf = send_request.attach_pdf if send_request else False
    with value_error_as_400():
        await service.send_proposal_email(proposal_id, current_user.id, attach_pdf)
    proposal = await get_entity_or_404(service, proposal_id, EntityNames.PROPOSAL)

    await emit(PROPOSAL_SENT, {
        "entity_id": proposal.id,
        "entity_type": "proposal",
        "user_id": current_user.id,
        "data": {"proposal_number": proposal.proposal_number, "status": proposal.status},
    })

    return ProposalResponse.model_validate(proposal)


@router.post("/{proposal_id}/restamp", response_model=ProposalResponse)
async def restamp_proposal_signed_pdf(
    proposal_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Retry the fail-soft accept-time signed-PDF stamp.

    Returns 200 in both success AND fail-soft cases — the frontend keys
    on ``signed_pdf_path`` (success) vs ``signed_pdf_error`` (still
    failing). Raising on the swallowed-error case would propagate past
    ``get_db``'s narrow exception handler and roll back the new error
    capture, leaving the operator looking at a stale message.
    """
    service = ProposalService(db)
    proposal = await get_entity_or_404(service, proposal_id, EntityNames.PROPOSAL)
    check_ownership(proposal, current_user, EntityNames.PROPOSAL)
    with value_error_as_400():
        proposal = await service.restamp_signed_pdf(proposal)
    return ProposalResponse.model_validate(proposal)


@router.get("/{proposal_id}/pdf")
async def get_proposal_pdf(
    proposal_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Branded proposal PDF; includes signature block when signed_at is set."""
    service = ProposalService(db)
    proposal = await get_entity_or_404(service, proposal_id, EntityNames.PROPOSAL)
    check_ownership(proposal, current_user, EntityNames.PROPOSAL)
    with value_error_as_400():
        pdf_bytes = await service.generate_proposal_pdf(
            proposal_id,
            current_user.id,
            include_signature=bool(proposal.signed_at),
        )
    suffix = "-signed" if proposal.signed_at else ""
    filename = f"proposal-{proposal.proposal_number}{suffix}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{proposal_id}/accept", response_model=ProposalResponse)
async def accept_proposal(
    proposal_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Mark a proposal as accepted (internal/admin path).

    Distinct from the public Sign-to-Confirm path at
    ``/public/{token}/accept`` — that flow captures a real customer
    signature plus IP/UA and verifies signer_email. This endpoint is
    the rep-side "the customer accepted offline" action — no
    signature, no e-sign payload. Fires the owner-side
    ``proposal_signed`` notification for parity but does not
    auto-spawn Stripe (Lorenzo bills manually via the Payments module
    per 2026-05-14).
    """
    service = ProposalService(db)
    proposal = await get_entity_or_404(service, proposal_id, EntityNames.PROPOSAL)
    check_ownership(proposal, current_user, EntityNames.PROPOSAL)
    with value_error_as_400():
        proposal = await service.mark_accepted(proposal)

    if proposal.owner_id and proposal.owner_id != current_user.id:
        from src.notifications.service import notify_on_proposal_signed

        try:
            await notify_on_proposal_signed(
                db=db,
                owner_id=proposal.owner_id,
                proposal_id=proposal.id,
                proposal_title=proposal.title,
                signer_name=None,
                signed_at=None,
            )
        except Exception:
            logger.exception(
                "proposal_signed notify failed (admin-accept) for proposal %s",
                proposal.id,
            )

    await emit(PROPOSAL_ACCEPTED, {
        "entity_id": proposal.id,
        "entity_type": "proposal",
        "user_id": current_user.id,
        "data": {"proposal_number": proposal.proposal_number, "status": proposal.status},
    })

    return ProposalResponse.model_validate(proposal)


@router.post("/{proposal_id}/duplicate", response_model=ProposalResponse, status_code=HTTPStatus.CREATED)
async def duplicate_proposal(
    proposal_id: int,
    request: Request,
    current_user: CurrentUser,
    db: DBSession,
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
):
    """Clone a proposal as a new draft.

    Copies core content + billing fields, appends " (copy)" to the title,
    and clears all e-sign / Stripe / sent timestamps. The clone is owned
    by the requesting user.
    """
    service = ProposalService(db)
    proposal = await get_entity_or_404(service, proposal_id, EntityNames.PROPOSAL)
    check_record_access_or_shared(
        proposal, current_user, data_scope.role_name,
        shared_entity_ids=data_scope.get_shared_ids(ENTITY_TYPE_PROPOSALS),
    )

    clone_data = ProposalCreate(
        title=f"{proposal.title} (copy)",
        content=proposal.content,
        cover_letter=proposal.cover_letter,
        executive_summary=proposal.executive_summary,
        scope_of_work=proposal.scope_of_work,
        pricing_section=proposal.pricing_section,
        timeline=proposal.timeline,
        terms=proposal.terms,
        valid_until=proposal.valid_until,
        opportunity_id=proposal.opportunity_id,
        contact_id=proposal.contact_id,
        company_id=proposal.company_id,
        quote_id=proposal.quote_id,
        payment_type=proposal.payment_type,
        recurring_interval=proposal.recurring_interval,
        recurring_interval_count=proposal.recurring_interval_count,
        amount=proposal.amount,
        currency=proposal.currency,
        designated_signer_email=proposal.designated_signer_email,
        status="draft",
    )

    with value_error_as_400():
        clone = await service.create(clone_data, current_user.id)

    ip_address = get_client_ip(request)
    await audit_entity_create(db, "proposal", clone.id, current_user.id, ip_address)

    return ProposalResponse.model_validate(clone)


@router.post("/{proposal_id}/reject", response_model=ProposalResponse)
async def reject_proposal(
    proposal_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Mark a proposal as rejected."""
    service = ProposalService(db)
    proposal = await get_entity_or_404(service, proposal_id, EntityNames.PROPOSAL)
    check_ownership(proposal, current_user, EntityNames.PROPOSAL)
    with value_error_as_400():
        proposal = await service.mark_rejected(proposal)

    await emit(PROPOSAL_REJECTED, {
        "entity_id": proposal.id,
        "entity_type": "proposal",
        "user_id": proposal.owner_id,
        "data": {"proposal_number": proposal.proposal_number, "status": proposal.status},
    })

    return ProposalResponse.model_validate(proposal)
