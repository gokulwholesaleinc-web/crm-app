"""Invoice send operations sub-router."""

import logging

from fastapi import APIRouter, HTTPException

from src.core.constants import HTTPStatus
from src.core.router_utils import CurrentUser, DBSession
from src.payments._router_helpers import (
    _verify_quote_access,
    _verify_stripe_customer_access,
)
from src.payments.schemas import (
    CreateAndSendInvoiceRequest,
    CreateAndSendInvoiceResponse,
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
        ) from e
