"""StripeCustomer endpoints sub-router."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from src.core.constants import HTTPStatus
from src.core.data_scope import DataScope, get_data_scope
from src.core.router_utils import (
    CurrentUser,
    DBSession,
    calculate_pages,
)
from src.payments._router_helpers import (
    _verify_company_access,
    _verify_contact_access,
)
from src.payments.schemas import (
    CreateOnboardingLinkRequest,
    CreateOnboardingLinkResponse,
    StripeCustomerListResponse,
    StripeCustomerResponse,
    SyncCustomerRequest,
)
from src.payments.service import PaymentService, StripeCustomerService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/customers", response_model=StripeCustomerListResponse)
async def list_customers(
    current_user: CurrentUser,
    db: DBSession,
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    contact_id: int | None = None,
    company_id: int | None = None,
):
    """List Stripe customers.

    Admin/manager see everyone; sales reps only see customers whose linked
    contact or company they own. StripeCustomer has no owner_id column, so
    visibility is derived from the contact/company joined relationships.

    ``contact_id`` / ``company_id`` filter by CRM linkage so callers
    that just want to know "does this contact already have a Stripe
    customer?" can do a 1-row check instead of paging the whole
    table client-side. Both filters are subject to the same access
    check the sync / onboarding-link endpoints use — a sales_rep
    passing an id they don't own gets 403, not an empty result that
    looks identical to "no customer exists." Without this gate the
    endpoint becomes a contact-existence oracle since
    ``c.contact.owner_id == current_user.id OR
    c.company.owner_id == current_user.id`` leaks rows whenever the
    queried contact happens to share a company the rep owns.
    """
    # Helpers no-op on None and on privileged roles, so calling
    # unconditionally is safe — privileged users still see everyone.
    await _verify_contact_access(db, contact_id, current_user)
    await _verify_company_access(db, company_id, current_user)

    service = StripeCustomerService(db)
    customers, total = await service.get_list(
        page=page, page_size=page_size,
        contact_id=contact_id, company_id=company_id,
    )

    if not data_scope.can_see_all():
        customers = [
            c for c in customers
            if (c.contact and c.contact.owner_id == current_user.id)
            or (c.company and c.company.owner_id == current_user.id)
        ]
        # ``total`` here is the visible page slice, not the global
        # match count — pre-existing oddity worth preserving the
        # current load-bearing semantics (the OnboardingLinkGenerator
        # frontend uses ``total > 0`` as a "has customer" check; it
        # works because page_size=1 + access check above means the
        # page is exactly the customer-or-not for that contact).
        # ``pages`` is recomputed off the now-filtered total so the
        # response stays internally consistent for any other caller
        # that paginates.
        total = len(customers)

    return StripeCustomerListResponse(
        items=[StripeCustomerResponse.model_validate(c) for c in customers],
        total=total,
        page=page,
        page_size=page_size,
        pages=calculate_pages(total, page_size),
    )


@router.post("/customers/sync", response_model=StripeCustomerResponse, status_code=HTTPStatus.CREATED)
async def sync_customer(
    request_data: SyncCustomerRequest,
    current_user: CurrentUser,
    db: DBSession,
):
    """Sync a CRM contact or company to a Stripe customer."""
    if request_data.contact_id is None and request_data.company_id is None:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="Either contact_id or company_id is required",
        )

    await _verify_contact_access(db, request_data.contact_id, current_user)
    await _verify_company_access(db, request_data.company_id, current_user)

    service = PaymentService(db)
    customer = await service.sync_customer(
        contact_id=request_data.contact_id,
        company_id=request_data.company_id,
    )
    return StripeCustomerResponse.model_validate(customer)


@router.post("/customers/onboarding-link", response_model=CreateOnboardingLinkResponse)
async def create_onboarding_link(
    request_data: CreateOnboardingLinkRequest,
    current_user: CurrentUser,
    db: DBSession,
):
    """Create a Stripe onboarding / setup link for a customer."""
    if request_data.contact_id is None and request_data.company_id is None:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="Either contact_id or company_id is required",
        )

    await _verify_contact_access(db, request_data.contact_id, current_user)
    await _verify_company_access(db, request_data.company_id, current_user)

    service = PaymentService(db)
    try:
        result = await service.create_onboarding_link(
            success_url=request_data.success_url,
            cancel_url=request_data.cancel_url,
            contact_id=request_data.contact_id,
            company_id=request_data.company_id,
        )
        return CreateOnboardingLinkResponse(**result)
    except ValueError as e:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=str(e),
        ) from e
