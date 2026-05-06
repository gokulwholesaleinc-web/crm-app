"""Payment records & Stripe payment operations sub-router."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select

from src.core.constants import ENTITY_TYPE_PAYMENTS, EntityNames, HTTPStatus
from src.core.data_scope import DataScope, check_record_access_or_shared, get_data_scope
from src.core.router_utils import (
    CurrentUser,
    DBSession,
    get_entity_or_404,
)
from src.core.opportunity_guards import assert_opportunity_active
from src.events.service import PAYMENT_RECEIVED, emit
from src.payments._router_helpers import (
    _verify_opportunity_access,
    _verify_quote_access,
    _verify_stripe_customer_access,
)
from src.payments.schemas import (
    CreateCheckoutRequest,
    CreateCheckoutResponse,
    CreatePaymentIntentRequest,
    CreatePaymentIntentResponse,
    PaymentResponse,
)
from src.payments.service import PaymentService

logger = logging.getLogger(__name__)

router = APIRouter()


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

    # Determine amount + opportunity link from quote if quote_id is provided.
    # The service already inherits quote.opportunity_id onto the Payment row,
    # so we have to gate on the source quote's opportunity here too — without
    # this guard, a Closed-Lost opportunity could still spawn a Stripe
    # Checkout Session via the quote-driven path.
    amount = request_data.amount
    quote_opportunity_id: int | None = None
    if request_data.quote_id:
        from src.quotes.models import Quote
        result = await db.execute(select(Quote).where(Quote.id == request_data.quote_id))
        quote = result.scalar_one_or_none()
        if not quote:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail="Quote not found",
            )
        if not amount:
            amount = quote.total
        quote_opportunity_id = quote.opportunity_id

    if not amount or amount <= 0:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="Amount must be greater than 0",
        )

    try:
        if quote_opportunity_id is not None:
            await assert_opportunity_active(db, quote_opportunity_id, "payment")
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
        ) from e


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
        if request_data.opportunity_id is not None:
            await assert_opportunity_active(db, request_data.opportunity_id, "payment")
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
        ) from e


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
        ) from e

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
        ) from e

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
        ) from e

    return {"message": "Receipt email sent", "payment_id": payment_id}


@router.post("/{payment_id}/send-invoice")
async def send_invoice(
    payment_id: int,
    current_user: CurrentUser,
    db: DBSession,
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
):
    """Resend the invoice email (with the rendered PDF attached)."""
    service = PaymentService(db)
    payment = await get_entity_or_404(service, payment_id, EntityNames.PAYMENT)
    check_record_access_or_shared(
        payment, current_user, data_scope.role_name,
        shared_entity_ids=data_scope.get_shared_ids(ENTITY_TYPE_PAYMENTS),
    )

    try:
        await service.send_payment_invoice(payment_id)
    except ValueError as e:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=str(e),
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=f"Failed to send invoice: {str(e)}",
        ) from e

    return {"message": "Invoice email sent", "payment_id": payment_id}


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
    await service.attach_proposals([payment])
    return PaymentResponse.model_validate(payment)
