"""Proposal API routes."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response

from src.audit.utils import (
    audit_entity_create,
    audit_entity_delete,
    audit_entity_update,
    snapshot_entity,
)
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
)
from src.events.service import PROPOSAL_ACCEPTED, PROPOSAL_SENT, emit
from src.proposals.schemas import (
    AIGenerateRequest,
    CreateFromTemplateRequest,
    ProposalAcceptRequest,
    ProposalBranding,
    ProposalCreate,
    ProposalListResponse,
    ProposalPublicResponse,
    ProposalRejectRequest,
    ProposalResponse,
    ProposalSendRequest,
    ProposalTemplateCreate,
    ProposalTemplateResponse,
    ProposalTemplateUpdate,
    ProposalUpdate,
)
from src.proposals.service import ProposalService, ProposalTemplateService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/proposals", tags=["proposals"])


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
    owner_id: int | None = None,
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
        owner_id=effective_owner_id,
        shared_entity_ids=data_scope.get_shared_ids(ENTITY_TYPE_PROPOSALS),
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
    proposal = await service.create(proposal_data, current_user.id)

    ip_address = request.client.host if request.client else None
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
    proposal = await service.create(proposal_data, current_user.id)

    ip_address = request.client.host if request.client else None
    await audit_entity_create(db, "proposal", proposal.id, current_user.id, ip_address)

    return ProposalResponse.model_validate(proposal)


@router.post("/generate", response_model=ProposalResponse, status_code=HTTPStatus.CREATED)
async def generate_proposal(
    request_data: AIGenerateRequest,
    current_user: CurrentUser,
    db: DBSession,
):
    """Generate a proposal using AI based on an opportunity."""
    from src.proposals.ai_generator import generate_proposal as ai_generate

    with value_error_as_400():
        proposal = await ai_generate(db, request_data.opportunity_id, current_user.id)
    return ProposalResponse.model_validate(proposal)


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
    ip_address = request.client.host if request.client else None
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
        footer_text=branding_data.get("footer_text"),
        privacy_policy_url=branding_data.get("privacy_policy_url"),
        terms_of_service_url=branding_data.get("terms_of_service_url"),
    )

    response = ProposalPublicResponse.model_validate(proposal)
    response.branding = branding
    return response


@router.post("/public/{token}/accept", response_model=ProposalPublicResponse)
@limiter.limit("10/minute")
async def accept_proposal_public(
    token: str,
    accept_data: ProposalAcceptRequest,
    request: Request,
    db: DBSession,
):
    """Accept a proposal via public link with e-signature data (no auth required).

    Captures signer name/email/IP/user-agent and transitions the proposal to
    ``accepted``. Rejects submissions whose signer_email does not match the
    proposal's ``designated_signer_email`` (or, failing that, the linked
    contact's email).
    """
    import hmac as _hmac

    service = ProposalService(db)
    proposal = await service.get_public_proposal(token)
    if not proposal or not _hmac.compare_digest(proposal.public_token or "", token):
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Proposal not found")

    signer_ip = request.client.host if request.client else None
    signer_user_agent = request.headers.get("user-agent")
    with value_error_as_400():
        proposal = await service.accept_proposal_public(
            proposal,
            signer_name=accept_data.signer_name,
            signer_email=accept_data.signer_email,
            signer_ip=signer_ip,
            signer_user_agent=signer_user_agent,
        )

    branding_data = await service.get_branding_for_proposal(proposal)
    response = ProposalPublicResponse.model_validate(proposal)
    response.branding = ProposalBranding(
        company_name=branding_data.get("company_name"),
        logo_url=branding_data.get("logo_url"),
        primary_color=branding_data.get("primary_color", "#6366f1"),
        secondary_color=branding_data.get("secondary_color", "#8b5cf6"),
        accent_color=branding_data.get("accent_color", "#22c55e"),
        footer_text=branding_data.get("footer_text"),
        privacy_policy_url=branding_data.get("privacy_policy_url"),
        terms_of_service_url=branding_data.get("terms_of_service_url"),
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

    signer_ip = request.client.host if request.client else None
    signer_user_agent = request.headers.get("user-agent")
    with value_error_as_400():
        proposal = await service.reject_proposal_public(
            proposal,
            reason=reject_data.reason,
            signer_ip=signer_ip,
            signer_user_agent=signer_user_agent,
            signer_email=reject_data.signer_email,
        )

    branding_data = await service.get_branding_for_proposal(proposal)
    response = ProposalPublicResponse.model_validate(proposal)
    response.branding = ProposalBranding(
        company_name=branding_data.get("company_name"),
        logo_url=branding_data.get("logo_url"),
        primary_color=branding_data.get("primary_color", "#6366f1"),
        secondary_color=branding_data.get("secondary_color", "#8b5cf6"),
        accent_color=branding_data.get("accent_color", "#22c55e"),
        footer_text=branding_data.get("footer_text"),
        privacy_policy_url=branding_data.get("privacy_policy_url"),
        terms_of_service_url=branding_data.get("terms_of_service_url"),
    )
    return response


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
    ip_address = request.client.host if request.client else None
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

    ip_address = request.client.host if request.client else None
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


@router.post("/{proposal_id}/retry-billing", response_model=ProposalResponse)
async def retry_proposal_billing(
    proposal_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Re-run the Stripe spawn for a proposal whose billing previously failed.

    Used after fixing a Stripe mis-configuration (missing key, wrong
    permissions) on an already-accepted proposal. Refuses if a payment
    URL is already present so we can't double-charge.
    """
    service = ProposalService(db)
    proposal = await get_entity_or_404(service, proposal_id, EntityNames.PROPOSAL)
    check_ownership(proposal, current_user, EntityNames.PROPOSAL)
    with value_error_as_400():
        proposal = await service.retry_billing(proposal)
    return ProposalResponse.model_validate(proposal)


@router.get("/{proposal_id}/pdf")
async def get_proposal_pdf(
    proposal_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Generate and return branded proposal PDF.

    If the proposal has been e-signed, the rendered PDF includes the
    signature block (signer name, email, timestamp, IP, user-agent) so
    the downloaded copy matches the signed-copy email sent to the
    customer on acceptance.
    """
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
    """Mark a proposal as accepted."""
    service = ProposalService(db)
    proposal = await get_entity_or_404(service, proposal_id, EntityNames.PROPOSAL)
    check_ownership(proposal, current_user, EntityNames.PROPOSAL)
    with value_error_as_400():
        proposal = await service.mark_accepted(proposal)

    await emit(PROPOSAL_ACCEPTED, {
        "entity_id": proposal.id,
        "entity_type": "proposal",
        "user_id": current_user.id,
        "data": {"proposal_number": proposal.proposal_number, "status": proposal.status},
    })

    return ProposalResponse.model_validate(proposal)


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
    return ProposalResponse.model_validate(proposal)
