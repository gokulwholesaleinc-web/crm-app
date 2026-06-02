"""Proposal API routes."""

import base64
import binascii
import logging
import re
from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse, Response
from sqlalchemy import select

from src.activities.models import Activity
from src.attachments.models import Attachment
from src.attachments.schemas import AttachmentListResponse, AttachmentResponse
from src.attachments.service import AttachmentService
from src.audit.utils import (
    audit_entity_create,
    audit_entity_delete,
    audit_entity_update,
    snapshot_entity,
)
from src.auth.models import User
from src.core.client_ip import get_client_ip
from src.core.constants import (
    ENTITY_TYPE_COMPANIES,
    ENTITY_TYPE_CONTACTS,
    ENTITY_TYPE_PROPOSALS,
    EntityNames,
    HTTPStatus,
)
from src.core.data_scope import DataScope, check_record_access_or_shared, get_data_scope
from src.core.http_errors import value_error_as_400
from src.core.permissions import require_permission
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
from src.onboarding.trigger import create_packet_and_send
from src.proposals.attachment_views import (
    ProposalAttachmentView,
    _hash_token,
    get_unviewed_attachment_ids,
    get_unviewed_signing_document_ids,
    record_attachment_view,
    record_signing_document_view,
)
from src.proposals.models import Proposal, ProposalSigningDocumentView
from src.proposals.schemas import (
    CreateFromTemplateRequest,
    ProposalAcceptRequest,
    ProposalAttachmentPublicItem,
    ProposalBranding,
    ProposalBundleCreate,
    ProposalBundleResponse,
    ProposalBundleUpdate,
    ProposalCreate,
    ProposalListResponse,
    ProposalPublicResponse,
    ProposalRejectRequest,
    ProposalResponse,
    ProposalSendRequest,
    ProposalSigningDocumentPublicItem,
    ProposalSigningDocumentResponse,
    ProposalSigningDocumentUpdate,
    ProposalTemplateCreate,
    ProposalTemplateResponse,
    ProposalTemplateUpdate,
    ProposalUpdate,
)
from src.proposals.service import (
    PROPOSAL_ESIGN_DISCLOSURE_VERSION,
    ProposalService,
    ProposalTemplateService,
    disclosure_company_name,
    proposal_esign_disclosure,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/proposals", tags=["proposals"])

# There is no live "proposals" permission domain. Staff proposal mutations
# are customer-facing sales writes, so gate them with contacts write
# permissions until a first-class proposals permission is introduced.
ProposalCreateUser = Annotated[User, Depends(require_permission("contacts", "create"))]
ProposalUpdateUser = Annotated[User, Depends(require_permission("contacts", "update"))]
ProposalDeleteUser = Annotated[User, Depends(require_permission("contacts", "delete"))]

# Hard cap on the raw signature_image payload (base64-encoded PNG)
# accepted by /public/{token}/accept. A typical drawn signature lands
# at ~5–30 KB; the cap keeps a hostile client from posting a multi-MB
# payload that would force the row into TOAST storage and bloat the
# audit page render.
_MAX_SIGNATURE_BYTES = 200_000
_MAX_SIGNING_PDF_BYTES = 25 * 1024 * 1024


def _require_declared_pdf_size(
    file: UploadFile,
    *,
    missing_detail: str,
    oversized_detail: str,
) -> None:
    """Reject uploads whose declared size is missing or over the PDF cap."""
    if file.size is None:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=missing_detail,
        )
    if file.size > _MAX_SIGNING_PDF_BYTES:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=oversized_detail,
        )


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
    # When false (default), bundle sub-options (sort_order > 0) are hidden
    # so the parent proposal surfaces as a single row on /proposals. The
    # admin RecordSearchPicker passes true so admins can still find and
    # share individual sub-options.
    include_bundle_options: bool = Query(False),
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
        include_bundle_options=include_bundle_options,
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
    current_user: ProposalCreateUser,
    db: DBSession,
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
):
    """Create a new proposal."""
    await _check_proposal_reference_access(db, proposal_data, current_user, data_scope)
    service = ProposalService(db)
    with value_error_as_400():
        proposal = await service.create(proposal_data, current_user.id)

    ip_address = get_client_ip(request)
    await audit_entity_create(db, "proposal", proposal.id, current_user.id, ip_address)

    return ProposalResponse.model_validate(proposal)


@router.post(
    "/bundles",
    response_model=ProposalBundleResponse,
    status_code=HTTPStatus.CREATED,
)
async def create_proposal_bundle(
    bundle_data: ProposalBundleCreate,
    request: Request,
    current_user: ProposalUpdateUser,
    db: DBSession,
):
    """Create a customer-facing bundle from two or more draft proposals."""
    await _require_proposals_write_access(db, bundle_data.proposal_ids, current_user)
    service = ProposalService(db)
    with value_error_as_400():
        bundle = await service.create_bundle(bundle_data, current_user.id)

    ip_address = get_client_ip(request)
    await audit_entity_create(db, "proposal_bundle", bundle.id, current_user.id, ip_address)
    return ProposalBundleResponse.model_validate(bundle)


@router.get("/bundles/{bundle_id}", response_model=ProposalBundleResponse)
async def get_proposal_bundle(
    bundle_id: int,
    current_user: CurrentUser,
    db: DBSession,
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
):
    """Get a proposal bundle by ID."""
    service = ProposalService(db)
    bundle = await service.get_bundle(bundle_id)
    if bundle is None:
        raise_not_found("Proposal bundle")
    _check_bundle_read_access(bundle, current_user, data_scope)
    return ProposalBundleResponse.model_validate(bundle)


@router.patch("/bundles/{bundle_id}", response_model=ProposalBundleResponse)
async def update_proposal_bundle(
    bundle_id: int,
    bundle_data: ProposalBundleUpdate,
    request: Request,
    current_user: ProposalUpdateUser,
    db: DBSession,
):
    """Update a draft proposal bundle."""
    if bundle_data.proposal_ids is not None:
        await _require_proposals_write_access(db, bundle_data.proposal_ids, current_user)
    service = ProposalService(db)
    # Mutation path → row-lock the bundle so concurrent PATCH / send /
    # remove-option callers serialize and can't co-corrupt membership.
    bundle = await service.get_bundle(bundle_id, for_update=True)
    if bundle is None:
        raise_not_found("Proposal bundle")
    _require_bundle_write_access(bundle, current_user)
    update_fields = list(bundle_data.model_dump(exclude_unset=True).keys())
    old_data = snapshot_entity(bundle, update_fields)
    with value_error_as_400():
        bundle = await service.update_bundle(bundle, bundle_data, current_user.id)
    # PATCH never carries proposal_ids with length 1 (schema-blocked), so
    # update_bundle can't return None here — narrow for the typechecker.
    assert bundle is not None
    new_data = snapshot_entity(bundle, update_fields)
    ip_address = get_client_ip(request)
    await audit_entity_update(
        db,
        "proposal_bundle",
        bundle.id,
        current_user.id,
        old_data,
        new_data,
        ip_address,
    )
    return ProposalBundleResponse.model_validate(bundle)


@router.post("/bundles/{bundle_id}/send", response_model=ProposalBundleResponse)
async def send_proposal_bundle(
    bundle_id: int,
    current_user: ProposalUpdateUser,
    db: DBSession,
):
    """Send one public chooser link for a proposal bundle."""
    service = ProposalService(db)
    # Send is a status-flip mutation that races with PATCH / remove-option.
    bundle = await service.get_bundle(bundle_id, for_update=True)
    if bundle is None:
        raise_not_found("Proposal bundle")
    _require_bundle_write_access(bundle, current_user)
    with value_error_as_400():
        bundle = await service.send_bundle_email(bundle_id, current_user.id)

    await emit(PROPOSAL_SENT, {
        "entity_id": bundle.id,
        "entity_type": "proposal_bundle",
        "user_id": current_user.id,
        "data": {"bundle_number": bundle.bundle_number, "status": bundle.status},
    })

    return ProposalBundleResponse.model_validate(bundle)


@router.delete("/bundles/{bundle_id}/options/{proposal_id}")
async def remove_proposal_bundle_option(
    bundle_id: int,
    proposal_id: int,
    request: Request,
    # Removing the second-to-last option dissolves the bundle (db.delete on
    # the ProposalBundle row). Gate on the same `delete` permission the
    # single-proposal DELETE and DELETE /bundles/{id} routes use — a user
    # holding only `update` shouldn't be able to destroy a bundle via the
    # remove-option side door.
    current_user: ProposalDeleteUser,
    db: DBSession,
):
    """Remove one proposal from a draft bundle.

    Returns 200 + the updated bundle when 2+ options remain. Returns 204
    when removing the option dissolved the bundle (≤1 survivor); the
    frontend should then navigate the user away from any sub-proposal
    detail page since the bundle no longer exists.
    """
    service = ProposalService(db)
    # Mutation path → row-lock the bundle so concurrent removes can't each
    # compute `survivors >= 2` from their own snapshot and leave a 1-option
    # zombie bundle. Same gate the PATCH / send paths use.
    bundle = await service.get_bundle(bundle_id, for_update=True)
    if bundle is None:
        raise_not_found("Proposal bundle")
    _require_bundle_write_access(bundle, current_user)
    # Confirm the proposal exists + the caller can write to it before we
    # mutate the bundle (avoids partial mutations on permission failures).
    await _require_proposals_write_access(db, [proposal_id], current_user)
    bundle_id_for_audit = bundle.id

    # snapshot_entity reads attributes by name and ProposalBundle exposes the
    # membership via the `proposals` relationship, not a flat `proposal_ids`
    # column — capture the id list explicitly so the audit log shows the
    # actual diff (e.g., [11, 12, 13] → [11, 12]).
    old_data = {"proposal_ids": [p.id for p in bundle.proposals]}
    with value_error_as_400():
        updated = await service.remove_option_from_bundle(
            bundle, proposal_id, current_user.id
        )
    ip_address = get_client_ip(request)
    if updated is None:
        # Bundle dissolved — log a delete on the parent + signal 204.
        await audit_entity_delete(
            db,
            "proposal_bundle",
            bundle_id_for_audit,
            current_user.id,
            ip_address,
        )
        return Response(status_code=HTTPStatus.NO_CONTENT)
    new_data = {"proposal_ids": [p.id for p in updated.proposals]}
    await audit_entity_update(
        db,
        "proposal_bundle",
        updated.id,
        current_user.id,
        old_data,
        new_data,
        ip_address,
    )
    return ProposalBundleResponse.model_validate(updated)


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
    current_user: ProposalCreateUser,
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
    current_user: ProposalUpdateUser,
    db: DBSession,
):
    """Update a proposal template."""
    service = ProposalTemplateService(db)
    template = await service.get_by_id(template_id)
    if not template:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Template not found")
    check_ownership(template, current_user, "proposal template")

    update_data = template_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(template, field, value)

    await db.flush()
    await db.refresh(template)
    return ProposalTemplateResponse.model_validate(template)


@router.delete("/templates/{template_id}", status_code=HTTPStatus.NO_CONTENT)
async def delete_template(
    template_id: int,
    current_user: ProposalDeleteUser,
    db: DBSession,
):
    """Delete a proposal template."""
    service = ProposalTemplateService(db)
    template = await service.get_by_id(template_id)
    if not template:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Template not found")
    check_ownership(template, current_user, "proposal template")
    await db.delete(template)
    await db.flush()


@router.post("/from-template", response_model=ProposalResponse, status_code=HTTPStatus.CREATED)
async def create_proposal_from_template(
    request_data: CreateFromTemplateRequest,
    request: Request,
    current_user: ProposalCreateUser,
    db: DBSession,
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
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
    check_record_access_or_shared(
        contact, current_user, data_scope.role_name,
        shared_entity_ids=data_scope.get_shared_ids(ENTITY_TYPE_CONTACTS),
    )

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
        check_record_access_or_shared(
            company, current_user, data_scope.role_name,
            shared_entity_ids=data_scope.get_shared_ids(ENTITY_TYPE_COMPANIES),
        )

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


async def _unviewed_public_document_count(
    db: DBSession,
    *,
    proposal_id: int,
    token: str,
) -> int:
    attachment_ids = await get_unviewed_attachment_ids(
        db,
        proposal_id=proposal_id,
        token=token,
    )
    signing_document_ids = await get_unviewed_signing_document_ids(
        db,
        proposal_id=proposal_id,
        token=token,
    )
    return len(attachment_ids) + len(signing_document_ids)


async def _attach_public_signing_documents(
    db: DBSession,
    response: ProposalPublicResponse,
    proposal,
    token: str,
    branding_data: dict | None = None,
) -> None:
    documents = list(proposal.signing_documents or [])
    response.signing_document_count = len(documents)
    response.has_master_contract = bool(
        proposal.master_contract_pdf_path or documents
    )
    response.esign_disclosure = proposal_esign_disclosure(
        has_signed_pdf_artifact=response.has_master_contract,
        company_name=disclosure_company_name(branding_data, proposal),
    )
    response.esign_disclosure_version = PROPOSAL_ESIGN_DISCLOSURE_VERSION
    if not documents:
        response.signing_documents = []
        return

    token_hash = _hash_token(token)
    viewed_rows = await db.execute(
        select(ProposalSigningDocumentView.document_id)
        .where(ProposalSigningDocumentView.token_hash == token_hash)
        .where(ProposalSigningDocumentView.document_id.in_([d.id for d in documents]))
    )
    viewed_ids = {r[0] for r in viewed_rows.all()}
    response.signing_documents = [
        ProposalSigningDocumentPublicItem(
            id=d.id,
            filename=d.original_filename,
            file_size=d.file_size,
            viewed=d.id in viewed_ids,
        )
        for d in documents
    ]


async def _raise_bundle_or_404(
    service: ProposalService,
    token: str,
    *,
    verb: str,
) -> NoReturn:
    """Resolve `token` as a bundle to give a meaningful error, or 404.

    Called from per-proposal accept/reject endpoints when the token doesn't
    match a proposal row. If it actually belongs to a bundle, return 409 when
    the bundle has already been selected, or 400 when the customer hasn't
    picked an option yet. `verb` is interpolated into the 400 message
    ("signing" / "rejecting").

    Always raises; never returns.
    """
    import hmac as _hmac  # noqa: PLC0415

    bundle = await service.get_public_bundle(token)
    if bundle and _hmac.compare_digest(bundle.public_token or "", token):
        if bundle.selected_proposal_id is not None or bundle.status == "accepted":
            raise HTTPException(
                status_code=HTTPStatus.CONFLICT,
                detail="This proposal bundle was already accepted",
            )
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=f"Pick a proposal option before {verb}",
        )
    raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Proposal not found")


def _branding_from_dict(data: dict | None) -> ProposalBranding:
    """Build a ProposalBranding from a TenantBrandingHelper dict.

    Centralizes the default color contract so a brand-default change is one
    edit. Was copy-pasted 4× across the public proposal routes.
    """
    data = data or {}
    return ProposalBranding(
        company_name=data.get("company_name"),
        logo_url=data.get("logo_url"),
        primary_color=data.get("primary_color", "#6366f1"),
        secondary_color=data.get("secondary_color", "#8b5cf6"),
        accent_color=data.get("accent_color", "#22c55e"),
        bg_color_light=data.get("bg_color_light", "#f9fafb"),
        surface_color_light=data.get("surface_color_light", "#ffffff"),
        footer_text=data.get("footer_text"),
        privacy_policy_url=data.get("privacy_policy_url"),
        terms_of_service_url=data.get("terms_of_service_url"),
    )


def _scope_public_payment_fields(response: ProposalPublicResponse) -> None:
    """Keep public payment compatibility only for active legacy pay links."""
    has_public_payment_flow = (
        response.status in {"awaiting_payment", "paid"}
        or bool(response.stripe_payment_url)
        or response.paid_at is not None
    )
    if has_public_payment_flow:
        return

    response.payment_type = None
    response.recurring_interval = None
    response.recurring_interval_count = None
    response.amount = None
    response.currency = None
    response.stripe_payment_url = None
    response.paid_at = None


async def _require_proposals_write_access(
    db: DBSession,
    proposal_ids: list[int],
    current_user: User,
) -> None:
    unique_ids = list(dict.fromkeys(proposal_ids))
    rows = await db.execute(select(Proposal).where(Proposal.id.in_(unique_ids)))
    proposals_by_id = {proposal.id: proposal for proposal in rows.scalars().all()}
    for proposal_id in unique_ids:
        proposal = proposals_by_id.get(proposal_id)
        if proposal is None:
            raise_not_found("Proposal")
        check_ownership(proposal, current_user, EntityNames.PROPOSAL)


def _require_bundle_write_access(bundle, current_user: User) -> None:
    if not bundle.proposals:
        if bundle.owner_id not in (None, current_user.id) and bundle.created_by_id != current_user.id:
            raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail="Access denied")
        return
    for proposal in bundle.proposals:
        check_ownership(proposal, current_user, EntityNames.PROPOSAL)


def _check_bundle_read_access(
    bundle,
    current_user: User,
    data_scope: DataScope,
) -> None:
    if data_scope.can_see_all():
        return
    if current_user.id in {bundle.owner_id, bundle.created_by_id}:
        return
    shared_proposal_ids = set(data_scope.get_shared_ids(ENTITY_TYPE_PROPOSALS))
    for proposal in bundle.proposals or []:
        if proposal.owner_id == current_user.id or proposal.id in shared_proposal_ids:
            return
    raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail="Access denied")


async def _check_proposal_reference_access(
    db: DBSession,
    proposal_data: ProposalCreate | ProposalUpdate,
    current_user: User,
    data_scope: DataScope,
) -> None:
    from src.companies.models import Company
    from src.contacts.models import Contact

    data = proposal_data.model_dump(exclude_unset=True)
    contact_id = data.get("contact_id")
    if contact_id is not None:
        contact = await db.get(Contact, contact_id)
        if contact is None:
            raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Contact not found")
        check_record_access_or_shared(
            contact, current_user, data_scope.role_name,
            shared_entity_ids=data_scope.get_shared_ids(ENTITY_TYPE_CONTACTS),
        )

    company_id = data.get("company_id")
    if company_id is not None:
        company = await db.get(Company, company_id)
        if company is None:
            raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Company not found")
        check_record_access_or_shared(
            company, current_user, data_scope.role_name,
            shared_entity_ids=data_scope.get_shared_ids(ENTITY_TYPE_COMPANIES),
        )


@router.post(
    "/{proposal_id}/attachments",
    response_model=AttachmentResponse,
    status_code=HTTPStatus.CREATED,
)
async def upload_proposal_attachment(
    proposal_id: int,
    current_user: ProposalUpdateUser,
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
    current_user: ProposalUpdateUser,
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
    when object storage isn't configured (dev/test). The public accept
    endpoint requires a view row for every proposal document.
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

    from src.attachments.object_storage import object_exists

    # Confirm the object actually exists before recording the view.
    # Presigning alone doesn't prove the key resolves — if the object
    # is missing the signer sees an R2 404 in the popup, but we'd
    # otherwise have already written a viewed row that lets the
    # read-before-sign gate pass.
    download_url: str | None = None
    file_path = None
    if attachment.file_path.startswith("obj://"):
        object_key = attachment.file_path[6:]
        try:
            exists = await object_exists(object_key)
        except Exception as exc:
            logger.info("R2 head_object failed for attachment %s: %s", attachment.id, exc)
            exists = False
        if not exists:
            raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="File not found")
        try:
            download_url = await att_service.get_download_url(attachment)
        except Exception as exc:
            logger.info("R2 presign failed for attachment %s: %s", attachment.id, exc)
            download_url = None
        if not download_url:
            raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="File not found")
    else:
        file_path = att_service.get_file_path(attachment)
        if not file_path or not file_path.exists():
            raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="File not found")

    # Record the view AFTER confirming the object is deliverable so a
    # missing R2 key can't write a "viewed" row that bypasses the gate.
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    await record_attachment_view(
        db,
        attachment_id=attachment.id,
        token=token,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    if download_url:
        return RedirectResponse(url=download_url, status_code=307)

    assert file_path is not None  # narrowed above
    return FileResponse(
        path=str(file_path),
        filename=attachment.original_filename,
        media_type=attachment.mime_type,
    )


@router.get("/public/{token}/signing-documents/{document_id}/download")
@limiter.limit("30/minute")
async def download_public_proposal_signing_document(
    token: str,
    document_id: int,
    request: Request,
    db: DBSession,
):
    """Public source-PDF download for signing documents.

    Opening this endpoint records the read-before-sign view row for the
    public token. The accept endpoint enforces that every regular
    attachment and every signing document has a matching view row.
    """
    import hmac as _hmac

    from botocore.exceptions import ClientError

    from src.attachments.object_storage import download_object_bytes

    service = ProposalService(db)
    proposal = await service.get_public_proposal(token)
    if not proposal or not _hmac.compare_digest(proposal.public_token or "", token):
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Proposal not found")

    document = await service.get_signing_document(proposal.id, document_id)
    if document is None:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail="Signing document not found",
        )

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
            "R2 ClientError fetching public signing document %s for proposal %s",
            document_id,
            proposal.id,
        )
        raise HTTPException(
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            detail="File storage temporarily unavailable — try again later",
        ) from exc
    except Exception as exc:
        logger.exception(
            "Unexpected error fetching public signing document %s for proposal %s",
            document_id,
            proposal.id,
        )
        raise HTTPException(
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            detail="File storage temporarily unavailable — try again later",
        ) from exc

    # Record the view AFTER the bytes are confirmed deliverable. If R2
    # fails or the proposal is missing the underlying object, we don't
    # want to claim the signer "viewed" a document they never received.
    ip_address = get_client_ip(request)
    user_agent = request.headers.get("user-agent")
    await record_signing_document_view(
        db,
        document_id=document.id,
        token=token,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{document.original_filename}"',
        },
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
    bundle = await service.get_public_bundle(token)
    if bundle and _hmac.compare_digest(bundle.public_token or "", token):
        await service.record_bundle_view(bundle)
        proposals = list(bundle.proposals or [])
        branding_data = (
            await service.get_branding_for_proposal(proposals[0])
            if proposals
            else {}
        )
        branding = _branding_from_dict(branding_data)

        option_responses: list[ProposalPublicResponse] = []
        for option in proposals:
            option_response = ProposalPublicResponse.model_validate(option)
            option_response.bundle_id = bundle.id
            option_response.bundle_title = bundle.title
            option_response.bundle_description = bundle.description
            option_response.bundle_selected_proposal_id = bundle.selected_proposal_id
            option_response.designated_signer_email = (
                option.designated_signer_email
                or (option.contact.email if option.contact else None)
            )
            option_response.has_master_contract = bool(
                option.master_contract_pdf_path or option.signing_documents
            )
            option_response.signing_document_count = len(option.signing_documents or [])
            option_response.attachments = []
            option_response.signing_documents = []
            _scope_public_payment_fields(option_response)
            option_responses.append(option_response)

        response = ProposalPublicResponse(
            id=None,
            proposal_number=bundle.bundle_number,
            public_token=bundle.public_token,
            title=bundle.title,
            content=bundle.description,
            status=bundle.status,
            bundle_id=bundle.id,
            bundle_title=bundle.title,
            bundle_description=bundle.description,
            bundle_selected_proposal_id=bundle.selected_proposal_id,
            proposal_options=option_responses,
            company=bundle.company,
            contact=bundle.contact,
            branding=branding,
        )
        _scope_public_payment_fields(response)
        return response

    proposal = await service.get_public_proposal(token)
    if not proposal or not _hmac.compare_digest(proposal.public_token or "", token):
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Proposal not found")

    # Record the view
    ip_address = get_client_ip(request)
    user_agent = request.headers.get("user-agent")
    await service.record_view(proposal.id, ip_address, user_agent)

    # Resolve branding from proposal owner's tenant
    branding_data = await service.get_branding_for_proposal(proposal)

    response = ProposalPublicResponse.model_validate(proposal)
    _scope_public_payment_fields(response)
    response.branding = _branding_from_dict(branding_data)
    response.designated_signer_email = (
        proposal.designated_signer_email
        or (proposal.contact.email if proposal.contact else None)
    )
    await _attach_public_signing_documents(db, response, proposal, token, branding_data)

    # Per-token attachment list — opening every document is required before
    # public signing, and the accept endpoint re-checks this server-side.
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
    composite to R2. No proposal-side Stripe spawn; any new payment
    collection starts in the Payments module per the 2026-05-14 product
    decision.
    """
    import hmac as _hmac

    service = ProposalService(db)
    proposal = await service.get_public_proposal(token)
    if not proposal or not _hmac.compare_digest(proposal.public_token or "", token):
        await _raise_bundle_or_404(service, token, verb="signing")

    unviewed_count = await _unviewed_public_document_count(
        db,
        proposal_id=proposal.id,
        token=token,
    )
    if unviewed_count:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=(
                "Open every proposal document before signing "
                f"({unviewed_count} remaining)"
            ),
        )

    signer_ip = get_client_ip(request)
    signer_user_agent = request.headers.get("user-agent")
    signature_bytes = _decode_signature_image(accept_data.signature_image)
    rejected_siblings: list = []
    with value_error_as_400():
        proposal, rejected_siblings = await service.accept_proposal_public(
            proposal,
            signer_name=accept_data.signer_name,
            signer_email=accept_data.signer_email,
            signature_image=signature_bytes,
            signer_ip=signer_ip,
            signer_user_agent=signer_user_agent,
            signer_timezone=accept_data.signer_timezone,
            selected_proposal_id=accept_data.selected_proposal_id,
        )

    # proposal_signed notification + email is dispatched by ProposalService.accept_proposal_public
    # via notify_on_proposal_signed (matrix-gated). Don't double-fire from the router.

    # Commit the accept (signature, consent snapshot, bundle sibling-rejections)
    # BEFORE the best-effort Phase-3 trigger so a trigger failure can never roll
    # it back, and a genuine commit failure surfaces (not swallowed). This is the
    # public path's only accept-commit point (get_db's end-of-request commit runs
    # AFTER the never-raises trigger, which may have rolled the session back).
    await db.commit()

    # Sibling rejections in a bundle: emit PROPOSAL_REJECTED per option that
    # was flipped to rejected by _mark_bundle_accepted, so the owner's
    # notifications matrix + reporting reflect the full picture (not just
    # the winner). Done post-accept so events fire outside the bundle row
    # lock acquired in accept_proposal_public.
    for sibling in rejected_siblings:
        await emit(PROPOSAL_REJECTED, {
            "entity_id": sibling.id,
            "entity_type": "proposal",
            "user_id": None,
            "data": {
                "proposal_number": sibling.proposal_number,
                "status": sibling.status,
                "rejected_via": "bundle_sibling",
                "reason": sibling.rejection_reason,
                "bundle_id": proposal.proposal_bundle_id,
                "accepted_proposal_id": proposal.id,
            },
        })

    branding_data = await service.get_branding_for_proposal(proposal)
    response = ProposalPublicResponse.model_validate(proposal)
    _scope_public_payment_fields(response)
    response.branding = _branding_from_dict(branding_data)
    response.designated_signer_email = (
        proposal.designated_signer_email
        or (proposal.contact.email if proposal.contact else None)
    )
    await _attach_public_signing_documents(db, response, proposal, token, branding_data)

    # Phase-3 auto-send LAST (after the response is fully built + every proposal
    # read): NEVER raises, kept OUTSIDE value_error_as_400 so a trigger issue
    # can't masquerade as a 400. Running it here means its internal
    # rollback-on-failure can't expire the object we just serialized.
    # Unauthenticated signer → actor_id=None.
    await create_packet_and_send(db, proposal=proposal, actor_id=None)
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
        await _raise_bundle_or_404(service, token, verb="rejecting")

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
    _scope_public_payment_fields(response)
    response.branding = _branding_from_dict(branding_data)
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
    current_user: ProposalUpdateUser,
    db: DBSession,
    file: UploadFile = File(...),
):
    """Upload one signable PDF. Every uploaded PDF needs a box before send."""
    service = ProposalService(db)
    proposal = await get_entity_or_404(service, proposal_id, EntityNames.PROPOSAL)
    check_ownership(proposal, current_user, EntityNames.PROPOSAL)
    _ensure_unsigned(proposal)
    _require_declared_pdf_size(
        file,
        missing_detail="signing document upload size is required",
        oversized_detail="signing document exceeds 25 MB limit",
    )
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
    current_user: ProposalUpdateUser,
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
            user_id=current_user.id,
            **document_data.model_dump(exclude_unset=True),
        )
    return ProposalSigningDocumentResponse.model_validate(document)


@router.delete(
    "/{proposal_id}/signing-documents/{document_id}",
    status_code=HTTPStatus.NO_CONTENT,
)
async def delete_signing_document(
    proposal_id: int,
    document_id: int,
    current_user: ProposalUpdateUser,
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
    current_user: ProposalUpdateUser,
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
    _require_declared_pdf_size(
        file,
        missing_detail="master contract upload size is required",
        oversized_detail="master contract exceeds 25 MB limit",
    )
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
    current_user: ProposalUpdateUser,
    db: DBSession,
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
):
    """Update a proposal."""
    await _check_proposal_reference_access(db, proposal_data, current_user, data_scope)
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
    current_user: ProposalDeleteUser,
    db: DBSession,
):
    """Delete a proposal.

    Bundle-aware: if the proposal belongs to a bundle, route through
    remove_option_from_bundle so survivors keep consistent sort_order
    and the bundle dissolves cleanly when ≤1 option remains.
    """
    service = ProposalService(db)
    proposal = await get_entity_or_404(service, proposal_id, EntityNames.PROPOSAL)
    check_ownership(proposal, current_user, EntityNames.PROPOSAL)

    ip_address = get_client_ip(request)
    await audit_entity_delete(db, "proposal", proposal.id, current_user.id, ip_address)

    with value_error_as_400():
        if proposal.proposal_bundle_id:
            bundle = await service.get_bundle(
                proposal.proposal_bundle_id, for_update=True
            )
            if bundle:
                await service.remove_option_from_bundle(
                    bundle, proposal_id, current_user.id
                )
        await service.delete(proposal)


@router.post("/{proposal_id}/send", response_model=ProposalResponse)
async def send_proposal(
    proposal_id: int,
    current_user: ProposalUpdateUser,
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
    current_user: ProposalUpdateUser,
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


@router.get("/{proposal_id}/signature")
async def get_proposal_signature_image(
    proposal_id: int,
    current_user: CurrentUser,
    db: DBSession,
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
):
    """Serve the captured e-signature PNG for the audit trail.

    Access mirrors the detail GET (owner or shared) since the image is
    surfaced on the same authed proposal page. The signature lives on the
    row as raw bytes — too large to ride on ``ProposalResponse`` (also the
    list payload) — so it gets its own endpoint. 404 when none was captured
    so the frontend hides the ``<img>`` without special-casing.
    """
    service = ProposalService(db)
    proposal = await get_entity_or_404(service, proposal_id, EntityNames.PROPOSAL)
    check_record_access_or_shared(
        proposal, current_user, data_scope.role_name,
        shared_entity_ids=data_scope.get_shared_ids(ENTITY_TYPE_PROPOSALS),
    )
    if proposal.signature_image is None:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail="No signature captured for this proposal",
        )
    return Response(
        content=proposal.signature_image,
        media_type="image/png",
        headers={"Cache-Control": "private, max-age=60"},
    )


async def _proposal_has_unsigned_signature_target(
    service: ProposalService, proposal: Proposal
) -> bool:
    """True iff the proposal expects a signature but none was captured (§E.1).

    A signature target is a master-contract sig box, a master-contract PDF on
    file, or any signing doc with its own sig box. ``signature_image is None``
    means no signature was ever drawn. Pure read — no lock needed.
    """
    if proposal.signature_image is not None:
        return False
    if (
        proposal.signature_field_coords is not None
        or proposal.master_contract_pdf_path is not None
    ):
        return True
    docs = await service.list_signing_documents(proposal.id)
    return any(d.signature_field_coords is not None for d in docs)


@router.post("/{proposal_id}/accept", response_model=ProposalResponse)
async def accept_proposal(
    proposal_id: int,
    current_user: ProposalUpdateUser,
    db: DBSession,
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
    acknowledge_unsigned: bool = Query(default=False),
):
    """Mark a proposal as accepted (internal/admin path).

    Distinct from the public Sign-to-Confirm path at
    ``/public/{token}/accept`` — that flow captures a real customer
    signature plus IP/UA and verifies signer_email. This endpoint is
    the rep-side "the customer accepted offline" action — no
    signature, no e-sign payload. Fires the owner-side
    ``proposal_signed`` notification for parity. It does not create a
    proposal-side payment link; any new collection starts in the Payments
    module per the 2026-05-14 product decision.

    Manual-confirmation guard (§E): if the proposal has a signature area but
    no signature on file, the accept is refused with 409 unless the caller
    re-submits with ``acknowledge_unsigned=true`` — recording an explicit
    offline acceptance without a signed document.
    """
    service = ProposalService(db)
    proposal = await get_entity_or_404(service, proposal_id, EntityNames.PROPOSAL)
    check_ownership(proposal, current_user, EntityNames.PROPOSAL)

    # E.2: pre-accept guard for an unsigned signature target.
    needs_confirmation = await _proposal_has_unsigned_signature_target(
        service, proposal
    )
    if needs_confirmation and not acknowledge_unsigned:
        raise HTTPException(
            status_code=HTTPStatus.CONFLICT,
            detail=(
                "This proposal has a signature area but no signature on file. "
                "Accepting it now records an offline acceptance without a "
                "signed document. Re-submit with acknowledgement to proceed."
            ),
        )

    with value_error_as_400():
        proposal = await service.mark_accepted(proposal)

    # E.3: audit a confirmed unsigned accept (durable proposal Activity).
    if needs_confirmation:
        signer = current_user.full_name or current_user.email
        db.add(
            Activity(
                activity_type="note",
                subject="Proposal manually accepted without signature",
                description=f"manually accepted without signature by {signer}",
                entity_type="proposals",
                entity_id=proposal.id,
                is_completed=True,
                completed_at=proposal.accepted_at,
                owner_id=proposal.owner_id,
                created_by_id=current_user.id,
            )
        )

    # Commit the accept (+ the manual-accept audit) BEFORE the best-effort
    # Phase-3 trigger so the trigger can never roll it back, and a genuine
    # commit failure surfaces instead of being swallowed by the never-raises
    # trigger.
    await db.commit()

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

    response = ProposalResponse.model_validate(proposal)

    # B: Phase-3 auto-send LAST — after every proposal read (notify/emit/response
    # build) so the trigger's internal rollback-on-failure can't expire the
    # serialized object (§E.4 / never-raises contract).
    await create_packet_and_send(db, proposal=proposal, actor_id=current_user.id)
    return response


# Matches a trailing " (copy)" or " (copy N)" suffix. Used to collapse copy
# chains (e.g. "foo (copy) (copy)" → "foo (copy 2)") so the Proposal Options
# panel doesn't accumulate "(copy) (copy) (copy)" titles after every Add.
_COPY_SUFFIX_RE = re.compile(r"\s*\(copy(?:\s+(\d+))?\)\s*$")


def _next_copy_title(title: str) -> str:
    base = title
    highest = 0
    chain_len = 0
    while True:
        m = _COPY_SUFFIX_RE.search(base)
        if not m:
            break
        chain_len += 1
        n = int(m.group(1)) if m.group(1) else 1
        highest = max(highest, n)
        base = base[: m.start()]
    # If the entire title was (copy)-suffixes (e.g. literal "(copy)"), there's
    # nothing meaningful to keep — fall back to suffixing the original title
    # rather than emitting a leading-space title like " (copy 2)".
    if chain_len == 0 or not base.strip():
        return f"{title} (copy)"
    # Use the larger of (highest explicit index, chain length) so legacy
    # `foo (copy) (copy)` collapses to `foo (copy 3)` rather than (copy 2).
    next_n = max(highest, chain_len) + 1
    return f"{base} (copy {next_n})"


@router.post("/{proposal_id}/duplicate", response_model=ProposalResponse, status_code=HTTPStatus.CREATED)
async def duplicate_proposal(
    proposal_id: int,
    request: Request,
    current_user: ProposalCreateUser,
    db: DBSession,
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
):
    """Clone a proposal as a new draft.

    Copies core proposal content, appends " (copy)" (or " (copy N)" when
    duplicating an existing copy) to the title, and clears all e-sign / Stripe
    / sent timestamps. Legacy structured payment fields are carried over for
    retention only; create/edit no longer exposes those inputs. The clone is
    owned by the requesting user.
    """
    service = ProposalService(db)
    proposal = await get_entity_or_404(service, proposal_id, EntityNames.PROPOSAL)
    check_record_access_or_shared(
        proposal, current_user, data_scope.role_name,
        shared_entity_ids=data_scope.get_shared_ids(ENTITY_TYPE_PROPOSALS),
    )

    clone_data = ProposalCreate(
        title=_next_copy_title(proposal.title),
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
        designated_signer_email=proposal.designated_signer_email,
        status="draft",
    )

    with value_error_as_400():
        clone = await service.create(clone_data, current_user.id)

    # Preserve legacy structured payment data on clones so old records are not
    # silently erased. These fields are read-only retention now; the form no
    # longer sends or edits them.
    clone.payment_type = proposal.payment_type
    clone.recurring_interval = proposal.recurring_interval
    clone.recurring_interval_count = proposal.recurring_interval_count
    clone.amount = proposal.amount
    clone.currency = proposal.currency
    await db.flush()
    await db.refresh(clone)

    ip_address = get_client_ip(request)
    await audit_entity_create(db, "proposal", clone.id, current_user.id, ip_address)

    return ProposalResponse.model_validate(clone)


@router.post("/{proposal_id}/reject", response_model=ProposalResponse)
async def reject_proposal(
    proposal_id: int,
    current_user: ProposalUpdateUser,
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
