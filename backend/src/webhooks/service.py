"""Webhook service layer for CRUD and delivery."""

import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone
from typing import Optional, List, Tuple, Dict, Any

import httpx
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.webhooks.models import Webhook, WebhookDelivery
from src.webhooks.schemas import WebhookCreate, WebhookUpdate
from src.core.base_service import BaseService
from src.core.constants import DEFAULT_PAGE_SIZE

logger = logging.getLogger(__name__)


def compute_signature(payload_bytes: bytes, secret: str) -> str:
    """Compute HMAC-SHA256 signature for webhook payload."""
    return hmac.new(
        secret.encode("utf-8"),
        payload_bytes,
        hashlib.sha256,
    ).hexdigest()


class WebhookService(BaseService[Webhook]):
    """Service for Webhook CRUD and delivery operations."""

    model = Webhook

    async def get_list(
        self,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
        is_active: Optional[bool] = None,
    ) -> Tuple[List[Webhook], int]:
        """Get paginated list of webhooks."""
        query = select(Webhook)

        if is_active is not None:
            query = query.where(Webhook.is_active == is_active)

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar()

        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(Webhook.created_at.desc())

        result = await self.db.execute(query)
        webhooks = list(result.scalars().all())
        return webhooks, total

    async def create_webhook(self, data: WebhookCreate, user_id: int) -> Webhook:
        """Create a new webhook."""
        webhook = Webhook(**data.model_dump(), created_by_id=user_id)
        self.db.add(webhook)
        await self.db.flush()
        await self.db.refresh(webhook)
        return webhook

    async def update_webhook(self, webhook: Webhook, data: WebhookUpdate) -> Webhook:
        """Update a webhook."""
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(webhook, field, value)
        await self.db.flush()
        await self.db.refresh(webhook)
        return webhook

    async def delete_webhook(self, webhook: Webhook) -> None:
        """Delete a webhook."""
        await self.db.delete(webhook)
        await self.db.flush()

    async def get_deliveries(
        self,
        webhook_id: int,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> Tuple[List[WebhookDelivery], int]:
        """Get delivery log for a webhook."""
        query = select(WebhookDelivery).where(WebhookDelivery.webhook_id == webhook_id)

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar()

        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(WebhookDelivery.attempted_at.desc())

        result = await self.db.execute(query)
        deliveries = list(result.scalars().all())
        return deliveries, total

    async def deliver_webhook(
        self,
        webhook: Webhook,
        event_type: str,
        payload: Dict[str, Any],
    ) -> WebhookDelivery:
        """Deliver a webhook: POST payload to webhook URL with signature header."""
        payload_bytes = json.dumps(payload, default=str).encode("utf-8")

        headers = {"Content-Type": "application/json"}
        if webhook.secret:
            signature = compute_signature(payload_bytes, webhook.secret)
            headers["X-Webhook-Signature"] = signature

        delivery = WebhookDelivery(
            webhook_id=webhook.id,
            event_type=event_type,
            payload=payload,
            status="pending",
        )

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    webhook.url,
                    content=payload_bytes,
                    headers=headers,
                )
                delivery.response_code = response.status_code
                delivery.status = "success" if response.status_code < 400 else "failed"
                if response.status_code >= 400:
                    delivery.error = response.text[:1000]
        except Exception as e:
            delivery.status = "failed"
            delivery.error = str(e)[:1000]

        self.db.add(delivery)
        await self.db.flush()
        await self.db.refresh(delivery)
        return delivery

    async def get_active_webhooks_for_event(self, event_type: str) -> List[Webhook]:
        """Get all active webhooks that subscribe to a given event type."""
        result = await self.db.execute(
            select(Webhook).where(Webhook.is_active == True)
        )
        webhooks = list(result.scalars().all())
        # Filter by event subscription (JSON list contains the event type)
        return [w for w in webhooks if event_type in (w.events or [])]
