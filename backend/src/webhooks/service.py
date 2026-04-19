"""Webhook service layer for CRUD and delivery."""

import hashlib
import hmac
import json
import logging
from typing import Any

import httpx
from sqlalchemy import func, select

from src.core.base_service import BaseService
from src.core.constants import DEFAULT_PAGE_SIZE
from src.webhooks.models import Webhook, WebhookDelivery
from src.webhooks.schemas import WebhookCreate, WebhookUpdate

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
        is_active: bool | None = None,
    ) -> tuple[list[Webhook], int]:
        """Get paginated list of webhooks."""
        query = select(Webhook)

        if is_active is not None:
            query = query.where(Webhook.is_active == is_active)

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(Webhook.created_at.desc())

        result = await self.db.execute(query)
        webhooks = list(result.scalars().all())
        return webhooks, total

    @staticmethod
    def _validate_webhook_url(url: str) -> None:
        """Reject private/internal URLs to prevent SSRF.

        Delegates to :func:`src.core.url_safety.validate_public_url`. A
        resolution failure at validation time is tolerated because webhook
        hosts may resolve only at delivery time (e.g. short-lived DNS),
        matching the legacy behavior. Any other failure surfaces as a
        ``ValueError`` because ``UnsafeUrlError`` is a ``ValueError``
        subclass, so the router's existing 400 handler picks it up.
        """
        from src.core.url_safety import UnsafeUrlError, validate_public_url

        try:
            validate_public_url(url)
        except UnsafeUrlError as exc:
            if "Could not resolve host" in str(exc):
                return  # legacy behavior: allow unresolvable hosts
            raise

    async def create_webhook(self, data: WebhookCreate, user_id: int) -> Webhook:
        self._validate_webhook_url(data.url)
        webhook = Webhook(**data.model_dump(), created_by_id=user_id)
        self.db.add(webhook)
        await self.db.flush()
        await self.db.refresh(webhook)
        return webhook

    async def update_webhook(self, webhook: Webhook, data: WebhookUpdate) -> Webhook:
        """Update a webhook.

        Re-runs SSRF validation on any URL change so an attacker cannot
        create a webhook pointing at ``https://example.com`` and then
        PATCH it to ``http://169.254.169.254/...`` to bypass the
        create-time check.
        """
        update_data = data.model_dump(exclude_unset=True)
        if "url" in update_data and update_data["url"]:
            self._validate_webhook_url(update_data["url"])
        for field, value in update_data.items():
            setattr(webhook, field, value)
        await self.db.flush()
        await self.db.refresh(webhook)
        return webhook

    async def delete_webhook(self, webhook: Webhook) -> None:
        await self.db.delete(webhook)
        await self.db.flush()

    async def get_deliveries(
        self,
        webhook_id: int,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> tuple[list[WebhookDelivery], int]:
        """Get delivery log for a webhook."""
        query = select(WebhookDelivery).where(WebhookDelivery.webhook_id == webhook_id)

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(WebhookDelivery.attempted_at.desc())

        result = await self.db.execute(query)
        deliveries = list(result.scalars().all())
        return deliveries, total

    async def deliver_webhook(
        self,
        webhook: Webhook,
        event_type: str,
        payload: dict[str, Any],
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

    async def get_active_webhooks_for_event(self, event_type: str) -> list[Webhook]:
        """Get all active webhooks that subscribe to a given event type."""
        result = await self.db.execute(
            select(Webhook).where(Webhook.is_active == True)
        )
        webhooks = list(result.scalars().all())
        # Filter by event subscription (JSON list contains the event type)
        return [w for w in webhooks if event_type in (w.events or [])]
