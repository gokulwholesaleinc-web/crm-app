"""Invoice send operations sub-router."""

import logging

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from src.core.constants import HTTPStatus
from src.core.opportunity_guards import assert_opportunity_active
from src.core.router_utils import CurrentUser, DBSession
from src.payments._router_helpers import (
    _verify_quote_access,
    _verify_stripe_customer_access,
)
from src.payments.schemas import (
    CreateAndSendInvoiceRequest,
    CreateAndSendInvoiceResponse,
    CreateSubscriptionCheckoutRequest,
    CreateSubscriptionCheckoutResponse,
)
from src.payments.service import PaymentService

logger = logging.getLogger(__name__)

router = APIRouter()


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

    # The service inherits quote.opportunity_id onto the spawned invoice
    # so a Closed-Lost opp could otherwise still receive a billable
    # invoice via the quote-driven path. Mirror the create-checkout guard.
    quote_opportunity_id: int | None = None
    if request_data.quote_id:
        from src.quotes.models import Quote
        result = await db.execute(select(Quote).where(Quote.id == request_data.quote_id))
        quote = result.scalar_one_or_none()
        if quote:
            quote_opportunity_id = quote.opportunity_id

    service = PaymentService(db)
    try:
        if quote_opportunity_id is not None:
            await assert_opportunity_active(db, quote_opportunity_id, "payment")
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
        ) from e


@router.post(
    "/subscriptions/create-and-send",
    response_model=CreateSubscriptionCheckoutResponse,
)
async def create_and_send_subscription(
    request_data: CreateSubscriptionCheckoutRequest,
    current_user: CurrentUser,
    db: DBSession,
):
    """Create a subscription Checkout Session for an existing Stripe customer."""
    if request_data.amount <= 0:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="Amount must be greater than 0",
        )

    await _verify_stripe_customer_access(db, request_data.customer_id, current_user)

    service = PaymentService(db)
    try:
        result = await service.create_and_send_subscription_checkout(
            customer_id=request_data.customer_id,
            amount=request_data.amount,
            description=request_data.description,
            user_id=current_user.id,
            currency=request_data.currency,
            interval=request_data.interval,
            interval_count=request_data.interval_count,
            success_url=request_data.success_url,
            cancel_url=request_data.cancel_url,
        )
        return CreateSubscriptionCheckoutResponse(**result)
    except ValueError as e:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=str(e),
        ) from e
