"""Subscription endpoints sub-router."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from src.core.constants import HTTPStatus
from src.core.data_scope import DataScope, get_data_scope
from src.core.router_utils import (
    CurrentUser,
    DBSession,
    calculate_pages,
    check_ownership,
)
from src.payments.schemas import (
    SubscriptionListResponse,
    SubscriptionResponse,
)
from src.payments.service import SubscriptionService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/subscriptions", response_model=SubscriptionListResponse)
async def list_subscriptions(
    current_user: CurrentUser,
    db: DBSession,
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = None,
    status_in: Annotated[list[str] | None, Query()] = None,
    customer_id: int | None = None,
    contact_id: int | None = None,
    company_id: int | None = None,
):
    """List subscriptions.

    ``contact_id`` / ``company_id`` filter by the CRM record linked to the
    Stripe customer — the Payments tab on contact/company detail pages
    pairs this with the payments list to show recurring billing too.

    ``status_in`` accepts repeated values (``?status_in=active&status_in=trialing``)
    so the contact "Subscriber" badge can count any Stripe state where
    billing is ongoing.
    """
    effective_owner_id = None
    if not data_scope.can_see_all():
        effective_owner_id = data_scope.owner_id

    service = SubscriptionService(db)
    subscriptions, total = await service.get_list(
        page=page,
        page_size=page_size,
        status=status,
        status_in=status_in,
        customer_id=customer_id,
        contact_id=contact_id,
        company_id=company_id,
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
