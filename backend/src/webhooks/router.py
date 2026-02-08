"""Webhook API routes."""

from typing import Optional, List
from fastapi import APIRouter, Query
from src.core.constants import HTTPStatus
from src.core.router_utils import DBSession, CurrentUser, raise_not_found
from src.webhooks.schemas import (
    WebhookCreate,
    WebhookUpdate,
    WebhookResponse,
    WebhookDeliveryResponse,
)
from src.webhooks.service import WebhookService

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


@router.post("", response_model=WebhookResponse, status_code=HTTPStatus.CREATED)
async def create_webhook(
    data: WebhookCreate,
    current_user: CurrentUser,
    db: DBSession,
):
    """Create a new webhook."""
    service = WebhookService(db)
    webhook = await service.create_webhook(data, current_user.id)
    return WebhookResponse.model_validate(webhook)


@router.get("", response_model=List[WebhookResponse])
async def list_webhooks(
    current_user: CurrentUser,
    db: DBSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    is_active: Optional[bool] = None,
):
    """List webhooks."""
    service = WebhookService(db)
    webhooks, _ = await service.get_list(
        page=page, page_size=page_size, is_active=is_active,
    )
    return [WebhookResponse.model_validate(w) for w in webhooks]


@router.get("/{webhook_id}", response_model=WebhookResponse)
async def get_webhook(
    webhook_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Get a webhook by ID."""
    service = WebhookService(db)
    webhook = await service.get_by_id(webhook_id)
    if not webhook:
        raise_not_found("Webhook", webhook_id)
    return WebhookResponse.model_validate(webhook)


@router.put("/{webhook_id}", response_model=WebhookResponse)
async def update_webhook(
    webhook_id: int,
    data: WebhookUpdate,
    current_user: CurrentUser,
    db: DBSession,
):
    """Update a webhook."""
    service = WebhookService(db)
    webhook = await service.get_by_id(webhook_id)
    if not webhook:
        raise_not_found("Webhook", webhook_id)
    updated = await service.update_webhook(webhook, data)
    return WebhookResponse.model_validate(updated)


@router.delete("/{webhook_id}", status_code=HTTPStatus.NO_CONTENT)
async def delete_webhook(
    webhook_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Delete a webhook."""
    service = WebhookService(db)
    webhook = await service.get_by_id(webhook_id)
    if not webhook:
        raise_not_found("Webhook", webhook_id)
    await service.delete_webhook(webhook)


@router.get("/{webhook_id}/deliveries", response_model=List[WebhookDeliveryResponse])
async def get_deliveries(
    webhook_id: int,
    current_user: CurrentUser,
    db: DBSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """Get delivery log for a webhook."""
    service = WebhookService(db)
    webhook = await service.get_by_id(webhook_id)
    if not webhook:
        raise_not_found("Webhook", webhook_id)
    deliveries, _ = await service.get_deliveries(webhook_id, page=page, page_size=page_size)
    return [WebhookDeliveryResponse.model_validate(d) for d in deliveries]


@router.post("/{webhook_id}/test")
async def test_webhook(
    webhook_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Send a test event to a webhook."""
    service = WebhookService(db)
    webhook = await service.get_by_id(webhook_id)
    if not webhook:
        raise_not_found("Webhook", webhook_id)

    test_payload = {
        "event": "webhook.test",
        "data": {
            "message": "This is a test webhook delivery",
            "webhook_id": webhook.id,
            "webhook_name": webhook.name,
        },
    }

    delivery = await service.deliver_webhook(webhook, "webhook.test", test_payload)
    return WebhookDeliveryResponse.model_validate(delivery)
