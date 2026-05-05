"""Payments API — composed from domain sub-routers."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from src.core.constants import ENTITY_TYPE_PAYMENTS
from src.core.data_scope import DataScope, get_data_scope
from src.core.router_utils import CurrentUser, DBSession, calculate_pages
from src.payments.routers import customers, diagnostics, invoices, payments, products, subscriptions
from src.payments.schemas import PaymentListResponse, PaymentResponse
from src.payments.service import PaymentService

router = APIRouter(prefix="/api/payments", tags=["payments"])


@router.get("", response_model=PaymentListResponse)
async def list_payments(
    current_user: CurrentUser,
    db: DBSession,
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = None,
    customer_id: int | None = None,
    contact_id: int | None = None,
    company_id: int | None = None,
    owner_id: int | None = None,
    search: str | None = None,
):
    """List payments with pagination and filters.

    ``contact_id`` / ``company_id`` show every payment for the CRM
    contact/company they map to via StripeCustomer — used by the Payments
    tab on the contact and company detail pages.
    """
    effective_owner_id = owner_id if data_scope.can_see_all() else data_scope.owner_id

    service = PaymentService(db)

    payments_list, total = await service.get_list(
        page=page,
        page_size=page_size,
        status=status,
        customer_id=customer_id,
        contact_id=contact_id,
        company_id=company_id,
        owner_id=effective_owner_id,
        shared_entity_ids=data_scope.get_shared_ids(ENTITY_TYPE_PAYMENTS),
        search=search,
    )

    await service.attach_proposals(payments_list)

    return PaymentListResponse(
        items=[PaymentResponse.model_validate(p) for p in payments_list],
        total=total,
        page=page,
        page_size=page_size,
        pages=calculate_pages(total, page_size),
    )


router.include_router(customers.router)
router.include_router(diagnostics.router)
router.include_router(invoices.router)
router.include_router(products.router)
router.include_router(subscriptions.router)
# payments.router MUST be last — it contains /{payment_id} catch-all routes
router.include_router(payments.router)
