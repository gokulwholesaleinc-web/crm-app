"""Quote API routes."""

import logging
from typing import Annotated, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from src.core.constants import HTTPStatus, EntityNames, ENTITY_TYPE_QUOTES
from src.core.router_utils import (
    DBSession,
    CurrentUser,
    get_entity_or_404,
    calculate_pages,
    check_ownership,
)
from src.core.data_scope import DataScope, get_data_scope, check_record_access_or_shared
from src.quotes.schemas import (
    QuoteCreate,
    QuoteUpdate,
    QuoteResponse,
    QuoteListResponse,
    QuoteLineItemCreate,
    QuoteLineItemResponse,
    QuoteBranding,
    QuotePublicResponse,
    QuoteAcceptRequest,
    QuoteRejectRequest,
    ProductBundleCreate,
    ProductBundleUpdate,
    ProductBundleResponse,
    ProductBundleListResponse,
)
from src.quotes.service import QuoteService, ProductBundleService
from src.audit.utils import audit_entity_create, audit_entity_update, audit_entity_delete, snapshot_entity
from src.events.service import emit, QUOTE_SENT, QUOTE_ACCEPTED

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/quotes", tags=["quotes"])


@router.get("", response_model=QuoteListResponse)
async def list_quotes(
    current_user: CurrentUser,
    db: DBSession,
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    status: Optional[str] = None,
    contact_id: Optional[int] = None,
    company_id: Optional[int] = None,
    opportunity_id: Optional[int] = None,
    owner_id: Optional[int] = None,
):
    """List quotes with pagination and filters."""
    if data_scope.can_see_all():
        effective_owner_id = owner_id
    else:
        effective_owner_id = data_scope.owner_id

    service = QuoteService(db)

    quotes, total = await service.get_list(
        page=page,
        page_size=page_size,
        search=search,
        status=status,
        contact_id=contact_id,
        company_id=company_id,
        opportunity_id=opportunity_id,
        owner_id=effective_owner_id,
        shared_entity_ids=data_scope.get_shared_ids(ENTITY_TYPE_QUOTES),
    )

    return QuoteListResponse(
        items=[QuoteResponse.model_validate(q) for q in quotes],
        total=total,
        page=page,
        page_size=page_size,
        pages=calculate_pages(total, page_size),
    )


@router.post("", response_model=QuoteResponse, status_code=HTTPStatus.CREATED)
async def create_quote(
    quote_data: QuoteCreate,
    request: Request,
    current_user: CurrentUser,
    db: DBSession,
):
    """Create a new quote."""
    service = QuoteService(db)
    quote = await service.create(quote_data, current_user.id)

    ip_address = request.client.host if request.client else None
    await audit_entity_create(db, "quote", quote.id, current_user.id, ip_address)

    return QuoteResponse.model_validate(quote)


# =============================================================================
# Bundle endpoints (BEFORE /{quote_id} to avoid path conflicts)
# =============================================================================

@router.get("/bundles", response_model=ProductBundleListResponse)
async def list_bundles(
    current_user: CurrentUser,
    db: DBSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    is_active: Optional[bool] = None,
):
    """List product bundles."""
    service = ProductBundleService(db)
    bundles, total = await service.get_list(
        page=page,
        page_size=page_size,
        search=search,
        is_active=is_active,
    )
    return ProductBundleListResponse(
        items=[ProductBundleResponse.model_validate(b) for b in bundles],
        total=total,
        page=page,
        page_size=page_size,
        pages=calculate_pages(total, page_size),
    )


@router.post("/bundles", response_model=ProductBundleResponse, status_code=HTTPStatus.CREATED)
async def create_bundle(
    bundle_data: ProductBundleCreate,
    current_user: CurrentUser,
    db: DBSession,
):
    """Create a product bundle."""
    service = ProductBundleService(db)
    bundle = await service.create(bundle_data, current_user.id)
    return ProductBundleResponse.model_validate(bundle)


@router.get("/bundles/{bundle_id}", response_model=ProductBundleResponse)
async def get_bundle(
    bundle_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Get a product bundle by ID."""
    service = ProductBundleService(db)
    bundle = await service.get_by_id(bundle_id)
    if not bundle:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Bundle not found")
    return ProductBundleResponse.model_validate(bundle)


@router.patch("/bundles/{bundle_id}", response_model=ProductBundleResponse)
async def update_bundle(
    bundle_id: int,
    bundle_data: ProductBundleUpdate,
    current_user: CurrentUser,
    db: DBSession,
):
    """Update a product bundle."""
    service = ProductBundleService(db)
    bundle = await service.get_by_id(bundle_id)
    if not bundle:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Bundle not found")
    updated = await service.update(bundle, bundle_data, current_user.id)
    return ProductBundleResponse.model_validate(updated)


@router.delete("/bundles/{bundle_id}", status_code=HTTPStatus.NO_CONTENT)
async def delete_bundle(
    bundle_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Delete a product bundle."""
    service = ProductBundleService(db)
    bundle = await service.get_by_id(bundle_id)
    if not bundle:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Bundle not found")
    await service.delete(bundle)


# =============================================================================
# Public quote endpoints (no auth, BEFORE /{quote_id} to avoid path conflicts)
# =============================================================================

@router.get("/public/{quote_number}", response_model=QuotePublicResponse)
async def get_public_quote(
    quote_number: str,
    request: Request,
    db: DBSession,
):
    """Public view of a quote (no auth required). Auto-transitions sent to viewed."""
    service = QuoteService(db)
    quote = await service.get_public_quote(quote_number)

    if not quote:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Quote not found")

    # Record the view (auto-transitions sent -> viewed)
    await service.record_quote_view(quote)

    # Resolve branding from quote owner's tenant
    branding_data = await service.get_branding_for_quote(quote)
    branding = QuoteBranding(
        company_name=branding_data.get("company_name"),
        logo_url=branding_data.get("logo_url"),
        primary_color=branding_data.get("primary_color", "#6366f1"),
        secondary_color=branding_data.get("secondary_color", "#8b5cf6"),
        accent_color=branding_data.get("accent_color", "#22c55e"),
        footer_text=branding_data.get("footer_text"),
    )

    response = QuotePublicResponse.model_validate(quote)
    response.branding = branding
    return response


@router.post("/public/{quote_number}/accept", response_model=QuotePublicResponse)
async def accept_quote_public(
    quote_number: str,
    accept_data: QuoteAcceptRequest,
    request: Request,
    db: DBSession,
):
    """Accept a quote via public link with e-signature data (no auth required)."""
    service = QuoteService(db)
    quote = await service.get_public_quote(quote_number)

    if not quote:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Quote not found")

    signer_ip = request.client.host if request.client else None
    try:
        quote = await service.accept_quote_public(
            quote,
            signer_name=accept_data.signer_name,
            signer_email=accept_data.signer_email,
            signer_ip=signer_ip,
        )
    except ValueError as e:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=str(e))

    branding_data = await service.get_branding_for_quote(quote)
    branding = QuoteBranding(
        company_name=branding_data.get("company_name"),
        logo_url=branding_data.get("logo_url"),
        primary_color=branding_data.get("primary_color", "#6366f1"),
        secondary_color=branding_data.get("secondary_color", "#8b5cf6"),
        accent_color=branding_data.get("accent_color", "#22c55e"),
        footer_text=branding_data.get("footer_text"),
    )

    response = QuotePublicResponse.model_validate(quote)
    response.branding = branding
    return response


@router.post("/public/{quote_number}/reject", response_model=QuotePublicResponse)
async def reject_quote_public(
    quote_number: str,
    request: Request,
    db: DBSession,
    reject_data: Optional[QuoteRejectRequest] = None,
):
    """Reject a quote via public link (no auth required)."""
    service = QuoteService(db)
    quote = await service.get_public_quote(quote_number)

    if not quote:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Quote not found")

    signer_ip = request.client.host if request.client else None
    reason = reject_data.reason if reject_data else None
    try:
        quote = await service.reject_quote_public(quote, reason=reason, signer_ip=signer_ip)
    except ValueError as e:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=str(e))

    branding_data = await service.get_branding_for_quote(quote)
    branding = QuoteBranding(
        company_name=branding_data.get("company_name"),
        logo_url=branding_data.get("logo_url"),
        primary_color=branding_data.get("primary_color", "#6366f1"),
        secondary_color=branding_data.get("secondary_color", "#8b5cf6"),
        accent_color=branding_data.get("accent_color", "#22c55e"),
        footer_text=branding_data.get("footer_text"),
    )

    response = QuotePublicResponse.model_validate(quote)
    response.branding = branding
    return response


# =============================================================================
# Quote detail endpoints
# =============================================================================

@router.get("/{quote_id}", response_model=QuoteResponse)
async def get_quote(
    quote_id: int,
    current_user: CurrentUser,
    db: DBSession,
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
):
    """Get a quote by ID with line items."""
    service = QuoteService(db)
    quote = await get_entity_or_404(service, quote_id, EntityNames.QUOTE)
    check_record_access_or_shared(
        quote, current_user, data_scope.role_name,
        shared_entity_ids=data_scope.get_shared_ids(ENTITY_TYPE_QUOTES),
    )
    return QuoteResponse.model_validate(quote)


@router.patch("/{quote_id}", response_model=QuoteResponse)
async def update_quote(
    quote_id: int,
    quote_data: QuoteUpdate,
    request: Request,
    current_user: CurrentUser,
    db: DBSession,
):
    """Update a quote."""
    service = QuoteService(db)
    quote = await get_entity_or_404(service, quote_id, EntityNames.QUOTE)
    check_ownership(quote, current_user, EntityNames.QUOTE)

    update_fields = list(quote_data.model_dump(exclude_unset=True).keys())
    old_data = snapshot_entity(quote, update_fields)

    updated_quote = await service.update(quote, quote_data, current_user.id)

    new_data = snapshot_entity(updated_quote, update_fields)
    ip_address = request.client.host if request.client else None
    await audit_entity_update(db, "quote", updated_quote.id, current_user.id, old_data, new_data, ip_address)

    return QuoteResponse.model_validate(updated_quote)


@router.delete("/{quote_id}", status_code=HTTPStatus.NO_CONTENT)
async def delete_quote(
    quote_id: int,
    request: Request,
    current_user: CurrentUser,
    db: DBSession,
):
    """Delete a quote."""
    service = QuoteService(db)
    quote = await get_entity_or_404(service, quote_id, EntityNames.QUOTE)
    check_ownership(quote, current_user, EntityNames.QUOTE)

    ip_address = request.client.host if request.client else None
    await audit_entity_delete(db, "quote", quote.id, current_user.id, ip_address)

    await service.delete(quote)


@router.post("/{quote_id}/send", response_model=QuoteResponse)
async def send_quote(
    quote_id: int,
    current_user: CurrentUser,
    db: DBSession,
    attach_pdf: bool = Query(False, description="Attach PDF to the email"),
):
    """Send a branded quote email to the contact and mark as sent."""
    service = QuoteService(db)
    quote = await get_entity_or_404(service, quote_id, EntityNames.QUOTE)
    check_ownership(quote, current_user, EntityNames.QUOTE)
    try:
        quote = await service.send_quote_email(quote_id, current_user.id, attach_pdf=attach_pdf)
    except ValueError as e:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=str(e))

    await emit(QUOTE_SENT, {
        "entity_id": quote.id,
        "entity_type": "quote",
        "user_id": current_user.id,
        "data": {"quote_number": quote.quote_number, "status": quote.status},
    })

    return QuoteResponse.model_validate(quote)


@router.get("/{quote_id}/pdf")
async def get_quote_pdf(
    quote_id: int,
    current_user: CurrentUser,
    db: DBSession,
    download: bool = Query(False, description="Force download instead of inline display"),
):
    """Generate and return a branded quote PDF."""
    service = QuoteService(db)
    quote = await get_entity_or_404(service, quote_id, EntityNames.QUOTE)
    check_ownership(quote, current_user, EntityNames.QUOTE)
    try:
        pdf_bytes = await service.generate_quote_pdf(quote_id, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=str(e))

    disposition = "attachment" if download else "inline"
    filename = f"quote-{quote.quote_number}.html"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'{disposition}; filename="{filename}"'},
    )


@router.post("/{quote_id}/accept", response_model=QuoteResponse)
async def accept_quote(
    quote_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Mark a quote as accepted."""
    service = QuoteService(db)
    quote = await get_entity_or_404(service, quote_id, EntityNames.QUOTE)
    check_ownership(quote, current_user, EntityNames.QUOTE)
    try:
        quote = await service.mark_accepted(quote)
    except ValueError as e:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=str(e))

    await emit(QUOTE_ACCEPTED, {
        "entity_id": quote.id,
        "entity_type": "quote",
        "user_id": current_user.id,
        "data": {"quote_number": quote.quote_number, "status": quote.status},
    })

    return QuoteResponse.model_validate(quote)


@router.post("/{quote_id}/reject", response_model=QuoteResponse)
async def reject_quote(
    quote_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Mark a quote as rejected."""
    service = QuoteService(db)
    quote = await get_entity_or_404(service, quote_id, EntityNames.QUOTE)
    check_ownership(quote, current_user, EntityNames.QUOTE)
    try:
        quote = await service.mark_rejected(quote)
    except ValueError as e:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=str(e))
    return QuoteResponse.model_validate(quote)


@router.post("/{quote_id}/line-items", response_model=QuoteLineItemResponse, status_code=HTTPStatus.CREATED)
async def add_line_item(
    quote_id: int,
    item_data: QuoteLineItemCreate,
    current_user: CurrentUser,
    db: DBSession,
):
    """Add a line item to a quote."""
    service = QuoteService(db)
    quote = await get_entity_or_404(service, quote_id, EntityNames.QUOTE)
    check_ownership(quote, current_user, EntityNames.QUOTE)
    item = await service.add_line_item(quote, item_data)
    return QuoteLineItemResponse.model_validate(item)


@router.delete("/{quote_id}/line-items/{item_id}", status_code=HTTPStatus.NO_CONTENT)
async def remove_line_item(
    quote_id: int,
    item_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Remove a line item from a quote."""
    service = QuoteService(db)
    quote = await get_entity_or_404(service, quote_id, EntityNames.QUOTE)
    check_ownership(quote, current_user, EntityNames.QUOTE)
    try:
        await service.remove_line_item(quote, item_id)
    except ValueError as e:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=str(e))


@router.post("/{quote_id}/add-bundle/{bundle_id}", response_model=QuoteResponse)
async def add_bundle_to_quote(
    quote_id: int,
    bundle_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Add all items from a product bundle to a quote."""
    service = QuoteService(db)
    quote = await get_entity_or_404(service, quote_id, EntityNames.QUOTE)
    check_ownership(quote, current_user, EntityNames.QUOTE)
    try:
        quote = await service.add_bundle_to_quote(quote, bundle_id)
    except ValueError as e:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=str(e))
    return QuoteResponse.model_validate(quote)
