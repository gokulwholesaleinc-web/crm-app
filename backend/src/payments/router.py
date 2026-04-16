"""Payment API routes."""

import logging
from typing import Annotated, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from src.core.constants import HTTPStatus, EntityNames, ENTITY_TYPE_PAYMENTS
from src.core.router_utils import (
    DBSession,
    CurrentUser,
    get_entity_or_404,
    calculate_pages,
    check_ownership,
    raise_forbidden,
)
from src.core.data_scope import DataScope, get_data_scope, check_record_access_or_shared
from src.payments.models import StripeCustomer
from src.payments.schemas import (
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
    CreateAndSendInvoiceRequest,
    CreateAndSendInvoiceResponse,
    CreateOnboardingLinkRequest,
    CreateOnboardingLinkResponse,
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


def _is_privileged(current_user) -> bool:
    """Admin/manager/superuser bypass ownership checks in this module."""
    if current_user.is_superuser:
        return True
    return getattr(current_user, "role", "sales_rep") in ("admin", "manager")


async def _verify_contact_access(db, contact_id: Optional[int], current_user) -> None:
    """Raise 403 if the caller cannot access the referenced contact."""
    if contact_id is None or _is_privileged(current_user):
        return
    from src.contacts.models import Contact
    result = await db.execute(select(Contact).where(Contact.id == contact_id))
    contact = result.scalar_one_or_none()
    if contact is None:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Contact not found")
    if contact.owner_id != current_user.id:
        raise_forbidden("You do not have permission to reference this contact")


async def _verify_company_access(db, company_id: Optional[int], current_user) -> None:
    """Raise 403 if the caller cannot access the referenced company."""
    if company_id is None or _is_privileged(current_user):
        return
    from src.companies.models import Company
    result = await db.execute(select(Company).where(Company.id == company_id))
    company = result.scalar_one_or_none()
    if company is None:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Company not found")
    if company.owner_id != current_user.id:
        raise_forbidden("You do not have permission to reference this company")


async def _verify_quote_access(db, quote_id: Optional[int], current_user) -> None:
    """Raise 403 if the caller cannot access the referenced quote."""
    if quote_id is None or _is_privileged(current_user):
        return
    from src.quotes.models import Quote
    result = await db.execute(select(Quote).where(Quote.id == quote_id))
    quote = result.scalar_one_or_none()
    if quote is None:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Quote not found")
    if quote.owner_id != current_user.id:
        raise_forbidden("You do not have permission to reference this quote")


async def _verify_opportunity_access(db, opportunity_id: Optional[int], current_user) -> None:
    """Raise 403 if the caller cannot access the referenced opportunity."""
    if opportunity_id is None or _is_privileged(current_user):
        return
    from src.opportunities.models import Opportunity
    result = await db.execute(select(Opportunity).where(Opportunity.id == opportunity_id))
    opp = result.scalar_one_or_none()
    if opp is None:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Opportunity not found")
    if opp.owner_id != current_user.id:
        raise_forbidden("You do not have permission to reference this opportunity")


async def _verify_stripe_customer_access(db, stripe_customer_id: int, current_user) -> StripeCustomer:
    """Load a StripeCustomer and raise 403 unless caller owns the linked contact/company.

    StripeCustomer has no `owner_id` column itself, so access is derived from
    whichever CRM entity (contact or company) it points at.
    """
    result = await db.execute(
        select(StripeCustomer).where(StripeCustomer.id == stripe_customer_id)
    )
    sc = result.scalar_one_or_none()
    if sc is None:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Stripe customer not found")
    if _is_privileged(current_user):
        return sc
    owner_ids = {
        sc.contact.owner_id if sc.contact else None,
        sc.company.owner_id if sc.company else None,
    }
    owner_ids.discard(None)
    if current_user.id not in owner_ids:
        raise_forbidden("You do not have permission to use this Stripe customer")
    return sc


# Payment List Endpoint (no path param conflict)

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
    search: Optional[str] = None,
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
        search=search,
    )

    return PaymentListResponse(
        items=[PaymentResponse.model_validate(p) for p in payments],
        total=total,
        page=page,
        page_size=page_size,
        pages=calculate_pages(total, page_size),
    )


# Checkout & Payment Intent Endpoints

@router.post("/create-checkout", response_model=CreateCheckoutResponse)
async def create_checkout(
    request_data: CreateCheckoutRequest,
    current_user: CurrentUser,
    db: DBSession,
):
    """Create a Stripe Checkout Session."""
    service = PaymentService(db)

    await _verify_quote_access(db, request_data.quote_id, current_user)
    if request_data.customer_id is not None:
        await _verify_stripe_customer_access(db, request_data.customer_id, current_user)

    # Determine amount from quote if quote_id is provided
    amount = request_data.amount
    if request_data.quote_id and not amount:
        from src.quotes.models import Quote
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

    await _verify_quote_access(db, request_data.quote_id, current_user)
    await _verify_opportunity_access(db, request_data.opportunity_id, current_user)
    if request_data.customer_id is not None:
        await _verify_stripe_customer_access(db, request_data.customer_id, current_user)

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


# Webhook Endpoint (no auth - uses Stripe signature verification)

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

    if result.get("event_type") in (
        "checkout.session.completed",
        "payment_intent.succeeded",
        "invoice.paid",
        "checkout.session.async_payment_succeeded",
    ):
        await emit(PAYMENT_RECEIVED, {
            "entity_id": None,
            "entity_type": "payment",
            "user_id": None,
            "data": {"event_type": result["event_type"], "event_id": result.get("event_id")},
        })

    return result


# Customer Endpoints

@router.get("/customers", response_model=StripeCustomerListResponse)
async def list_customers(
    current_user: CurrentUser,
    db: DBSession,
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List Stripe customers.

    Admin/manager see everyone; sales reps only see customers whose linked
    contact or company they own. StripeCustomer has no owner_id column, so
    visibility is derived from the contact/company joined relationships.
    """
    service = StripeCustomerService(db)
    customers, total = await service.get_list(page=page, page_size=page_size)

    if not data_scope.can_see_all():
        customers = [
            c for c in customers
            if (c.contact and c.contact.owner_id == current_user.id)
            or (c.company and c.company.owner_id == current_user.id)
        ]
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
        )


# Invoice Endpoints

@router.post("/invoices/create-and-send", response_model=CreateAndSendInvoiceResponse)
async def create_and_send_invoice(
    request_data: CreateAndSendInvoiceRequest,
    current_user: CurrentUser,
    db: DBSession,
):
    """Create, finalize, and send a Stripe invoice."""
    if request_data.amount <= 0:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="Amount must be greater than 0",
        )

    await _verify_stripe_customer_access(db, request_data.customer_id, current_user)
    await _verify_quote_access(db, request_data.quote_id, current_user)

    service = PaymentService(db)
    try:
        result = await service.create_and_send_invoice(
            customer_id=request_data.customer_id,
            amount=float(request_data.amount),
            description=request_data.description,
            user_id=current_user.id,
            currency=request_data.currency,
            due_days=request_data.due_days,
            quote_id=request_data.quote_id,
            payment_method_types=request_data.payment_method_types,
        )
        return CreateAndSendInvoiceResponse(**result)
    except ValueError as e:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=str(e),
        )


# Product Endpoints

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


# Subscription Endpoints

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
    check_ownership(subscription, current_user, "subscription")
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
    check_ownership(subscription, current_user, "subscription")
    subscription = await service.cancel(subscription)
    return SubscriptionResponse.model_validate(subscription)


# Invoice & Receipt Endpoints (MUST be before /{payment_id} catch-all)

@router.get("/{payment_id}/invoice")
async def download_invoice(
    payment_id: int,
    current_user: CurrentUser,
    db: DBSession,
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
):
    """Generate and return branded invoice PDF (HTML) for a payment."""
    from fastapi.responses import Response

    service = PaymentService(db)
    payment = await get_entity_or_404(service, payment_id, EntityNames.PAYMENT)
    check_record_access_or_shared(
        payment, current_user, data_scope.role_name,
        shared_entity_ids=data_scope.get_shared_ids(ENTITY_TYPE_PAYMENTS),
    )

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
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
):
    """Manually resend receipt email for a payment."""
    service = PaymentService(db)
    payment = await get_entity_or_404(service, payment_id, EntityNames.PAYMENT)
    check_record_access_or_shared(
        payment, current_user, data_scope.role_name,
        shared_entity_ids=data_scope.get_shared_ids(ENTITY_TYPE_PAYMENTS),
    )

    try:
        await service.send_payment_receipt(payment_id)
    except Exception as e:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=f"Failed to send receipt: {str(e)}",
        )

    return {"message": "Receipt email sent", "payment_id": payment_id}


# Payment Detail Endpoint (MUST be last - path param catches all)

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
