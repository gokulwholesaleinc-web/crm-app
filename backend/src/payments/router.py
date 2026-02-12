"""Payment API routes."""

import logging
from typing import Annotated, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from src.core.constants import HTTPStatus, EntityNames, ENTITY_TYPE_PAYMENTS
from src.core.router_utils import (
    DBSession,
    CurrentUser,
    get_entity_or_404,
    calculate_pages,
    check_ownership,
)
from src.core.data_scope import DataScope, get_data_scope, check_record_access_or_shared
from src.payments.schemas import (
    PaymentCreate,
    PaymentResponse,
    PaymentListResponse,
    ProductCreate,
    ProductResponse,
    ProductListResponse,
    StripeCustomerResponse,
    StripeCustomerListResponse,
    SyncCustomerRequest,
    SubscriptionResponse,
    SubscriptionListResponse,
    CreateCheckoutRequest,
    CreateCheckoutResponse,
    CreatePaymentIntentRequest,
    CreatePaymentIntentResponse,
)
from src.payments.service import (
    PaymentService,
    ProductService,
    StripeCustomerService,
    SubscriptionService,
)
from src.events.service import emit, PAYMENT_RECEIVED

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/payments", tags=["payments"])


# =============================================================================
# Payment List Endpoint (no path param conflict)
# =============================================================================

@router.get("", response_model=PaymentListResponse)
async def list_payments(
    current_user: CurrentUser,
    db: DBSession,
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    customer_id: Optional[int] = None,
    owner_id: Optional[int] = None,
):
    """List payments with pagination and filters."""
    if data_scope.can_see_all():
        effective_owner_id = owner_id
    else:
        effective_owner_id = data_scope.owner_id

    service = PaymentService(db)

    payments, total = await service.get_list(
        page=page,
        page_size=page_size,
        status=status,
        customer_id=customer_id,
        owner_id=effective_owner_id,
        shared_entity_ids=data_scope.get_shared_ids(ENTITY_TYPE_PAYMENTS),
    )

    return PaymentListResponse(
        items=[PaymentResponse.model_validate(p) for p in payments],
        total=total,
        page=page,
        page_size=page_size,
        pages=calculate_pages(total, page_size),
    )


# =============================================================================
# Checkout & Payment Intent Endpoints
# =============================================================================

@router.post("/create-checkout", response_model=CreateCheckoutResponse)
async def create_checkout(
    request_data: CreateCheckoutRequest,
    current_user: CurrentUser,
    db: DBSession,
):
    """Create a Stripe Checkout Session."""
    service = PaymentService(db)

    # Determine amount from quote if quote_id is provided
    amount = request_data.amount
    if request_data.quote_id and not amount:
        from src.quotes.models import Quote
        from sqlalchemy import select
        result = await db.execute(select(Quote).where(Quote.id == request_data.quote_id))
        quote = result.scalar_one_or_none()
        if not quote:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail="Quote not found",
            )
        amount = quote.total

    if not amount or amount <= 0:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="Amount must be greater than 0",
        )

    try:
        result = await service.create_checkout_session(
            amount=amount,
            currency=request_data.currency,
            success_url=request_data.success_url,
            cancel_url=request_data.cancel_url,
            user_id=current_user.id,
            customer_id=request_data.customer_id,
            quote_id=request_data.quote_id,
        )
        return CreateCheckoutResponse(**result)
    except ValueError as e:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=str(e),
        )


@router.post("/create-payment-intent", response_model=CreatePaymentIntentResponse)
async def create_payment_intent(
    request_data: CreatePaymentIntentRequest,
    current_user: CurrentUser,
    db: DBSession,
):
    """Create a Stripe PaymentIntent."""
    if request_data.amount <= 0:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="Amount must be greater than 0",
        )

    service = PaymentService(db)

    try:
        result = await service.create_payment_intent(
            amount=request_data.amount,
            currency=request_data.currency,
            user_id=current_user.id,
            customer_id=request_data.customer_id,
            opportunity_id=request_data.opportunity_id,
            quote_id=request_data.quote_id,
        )
        return CreatePaymentIntentResponse(**result)
    except ValueError as e:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=str(e),
        )


# =============================================================================
# Webhook Endpoint (no auth - uses Stripe signature verification)
# =============================================================================

@router.post("/webhook")
async def stripe_webhook(request: Request, db: DBSession):
    """Handle Stripe webhook events.

    This endpoint has NO authentication - it relies on Stripe signature verification.
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    service = PaymentService(db)
    try:
        result = await service.process_webhook(payload, sig_header)
    except ValueError as e:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=str(e),
        )

    if result.get("event_type") in ("checkout.session.completed", "payment_intent.succeeded"):
        await emit(PAYMENT_RECEIVED, {
            "entity_id": None,
            "entity_type": "payment",
            "user_id": None,
            "data": {"event_type": result["event_type"], "event_id": result.get("event_id")},
        })

    return result


# =============================================================================
# Customer Endpoints
# =============================================================================

@router.get("/customers", response_model=StripeCustomerListResponse)
async def list_customers(
    current_user: CurrentUser,
    db: DBSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List Stripe customers."""
    service = StripeCustomerService(db)
    customers, total = await service.get_list(page=page, page_size=page_size)

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
    if not request_data.contact_id and not request_data.company_id:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="Either contact_id or company_id is required",
        )

    service = PaymentService(db)
    customer = await service.sync_customer(
        contact_id=request_data.contact_id,
        company_id=request_data.company_id,
    )
    return StripeCustomerResponse.model_validate(customer)


# =============================================================================
# Product Endpoints
# =============================================================================

@router.get("/products", response_model=ProductListResponse)
async def list_products(
    current_user: CurrentUser,
    db: DBSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    is_active: Optional[bool] = None,
):
    """List products."""
    service = ProductService(db)
    products, total = await service.get_list(
        page=page,
        page_size=page_size,
        is_active=is_active,
    )

    return ProductListResponse(
        items=[ProductResponse.model_validate(p) for p in products],
        total=total,
        page=page,
        page_size=page_size,
        pages=calculate_pages(total, page_size),
    )


@router.post("/products", response_model=ProductResponse, status_code=HTTPStatus.CREATED)
async def create_product(
    product_data: ProductCreate,
    current_user: CurrentUser,
    db: DBSession,
):
    """Create a new product."""
    service = ProductService(db)
    product = await service.create(product_data, current_user.id)
    return ProductResponse.model_validate(product)


# =============================================================================
# Subscription Endpoints
# =============================================================================

@router.get("/subscriptions", response_model=SubscriptionListResponse)
async def list_subscriptions(
    current_user: CurrentUser,
    db: DBSession,
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    customer_id: Optional[int] = None,
):
    """List subscriptions."""
    effective_owner_id = None
    if not data_scope.can_see_all():
        effective_owner_id = data_scope.owner_id

    service = SubscriptionService(db)
    subscriptions, total = await service.get_list(
        page=page,
        page_size=page_size,
        status=status,
        customer_id=customer_id,
        owner_id=effective_owner_id,
    )

    return SubscriptionListResponse(
        items=[SubscriptionResponse.model_validate(s) for s in subscriptions],
        total=total,
        page=page,
        page_size=page_size,
        pages=calculate_pages(total, page_size),
    )


@router.get("/subscriptions/{subscription_id}", response_model=SubscriptionResponse)
async def get_subscription(
    subscription_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Get a subscription by ID."""
    service = SubscriptionService(db)
    subscription = await service.get_by_id(subscription_id)
    if not subscription:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail="Subscription not found",
        )
    return SubscriptionResponse.model_validate(subscription)


@router.post("/subscriptions/{subscription_id}/cancel", response_model=SubscriptionResponse)
async def cancel_subscription(
    subscription_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Cancel a subscription."""
    service = SubscriptionService(db)
    subscription = await service.get_by_id(subscription_id)
    if not subscription:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail="Subscription not found",
        )
    subscription = await service.cancel(subscription)
    return SubscriptionResponse.model_validate(subscription)


# =============================================================================
# Invoice & Receipt Endpoints (MUST be before /{payment_id} catch-all)
# =============================================================================

@router.get("/{payment_id}/invoice")
async def download_invoice(
    payment_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Generate and return branded invoice PDF (HTML) for a payment."""
    from fastapi.responses import Response

    service = PaymentService(db)
    payment = await get_entity_or_404(service, payment_id, EntityNames.PAYMENT)

    try:
        pdf_bytes = await service.generate_invoice_pdf(payment_id)
    except ValueError as e:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail=str(e),
        )

    return Response(
        content=pdf_bytes,
        media_type="text/html",
        headers={
            "Content-Disposition": f'inline; filename="invoice-{payment_id}.html"',
        },
    )


@router.post("/{payment_id}/send-receipt")
async def send_receipt(
    payment_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Manually resend receipt email for a payment."""
    service = PaymentService(db)
    payment = await get_entity_or_404(service, payment_id, EntityNames.PAYMENT)

    try:
        await service.send_payment_receipt(payment_id)
    except Exception as e:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=f"Failed to send receipt: {str(e)}",
        )

    return {"message": "Receipt email sent", "payment_id": payment_id}


# =============================================================================
# Payment Detail Endpoint (MUST be last - path param catches all)
# =============================================================================

@router.get("/{payment_id}", response_model=PaymentResponse)
async def get_payment(
    payment_id: int,
    current_user: CurrentUser,
    db: DBSession,
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
):
    """Get a payment by ID."""
    service = PaymentService(db)
    payment = await get_entity_or_404(service, payment_id, EntityNames.PAYMENT)
    check_record_access_or_shared(
        payment, current_user, data_scope.role_name,
        shared_entity_ids=data_scope.get_shared_ids(ENTITY_TYPE_PAYMENTS),
    )
    return PaymentResponse.model_validate(payment)
