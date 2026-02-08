"""
Unit tests for webhook endpoints and event system.

Tests webhook CRUD, HMAC signature verification, delivery logging, and event emission.
"""

import hashlib
import hmac
import json
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.auth.models import User
from src.webhooks.models import Webhook, WebhookDelivery
from src.webhooks.service import compute_signature
from src.events.service import emit, on, off, clear_handlers, get_handlers


@pytest.fixture
async def test_webhook(db_session: AsyncSession, test_user: User) -> Webhook:
    """Create a test webhook."""
    webhook = Webhook(
        name="Test Webhook",
        url="https://example.com/webhook",
        events=["lead.created", "lead.updated"],
        secret="test-secret-123",
        is_active=True,
        created_by_id=test_user.id,
    )
    db_session.add(webhook)
    await db_session.commit()
    await db_session.refresh(webhook)
    return webhook


class TestWebhookCRUD:
    """Tests for webhook CRUD endpoints."""

    @pytest.mark.asyncio
    async def test_create_webhook(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test creating a new webhook."""
        response = await client.post(
            "/api/webhooks",
            headers=auth_headers,
            json={
                "name": "My Webhook",
                "url": "https://example.com/hook",
                "events": ["lead.created", "contact.created"],
                "secret": "my-secret",
                "is_active": True,
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "My Webhook"
        assert data["url"] == "https://example.com/hook"
        assert "lead.created" in data["events"]
        assert "contact.created" in data["events"]
        assert data["is_active"] is True
        assert "id" in data

    @pytest.mark.asyncio
    async def test_create_webhook_minimal(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test creating webhook with minimal fields."""
        response = await client.post(
            "/api/webhooks",
            headers=auth_headers,
            json={
                "name": "Simple Webhook",
                "url": "https://example.com/simple",
                "events": ["lead.created"],
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Simple Webhook"
        assert data["secret"] is None

    @pytest.mark.asyncio
    async def test_list_webhooks(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_webhook: Webhook,
    ):
        """Test listing webhooks."""
        response = await client.get(
            "/api/webhooks",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert any(w["id"] == test_webhook.id for w in data)

    @pytest.mark.asyncio
    async def test_list_webhooks_filter_active(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_webhook: Webhook,
    ):
        """Test filtering webhooks by active status."""
        response = await client.get(
            "/api/webhooks",
            headers=auth_headers,
            params={"is_active": True},
        )

        assert response.status_code == 200
        data = response.json()
        assert all(w["is_active"] for w in data)

    @pytest.mark.asyncio
    async def test_get_webhook(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_webhook: Webhook,
    ):
        """Test getting a webhook by ID."""
        response = await client.get(
            f"/api/webhooks/{test_webhook.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == test_webhook.id
        assert data["name"] == "Test Webhook"

    @pytest.mark.asyncio
    async def test_get_webhook_not_found(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test getting non-existent webhook returns 404."""
        response = await client.get(
            "/api/webhooks/99999",
            headers=auth_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_webhook(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_webhook: Webhook,
    ):
        """Test updating a webhook."""
        response = await client.put(
            f"/api/webhooks/{test_webhook.id}",
            headers=auth_headers,
            json={
                "name": "Updated Webhook",
                "is_active": False,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Webhook"
        assert data["is_active"] is False
        # Unchanged fields
        assert data["url"] == "https://example.com/webhook"

    @pytest.mark.asyncio
    async def test_delete_webhook(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Test deleting a webhook."""
        webhook = Webhook(
            name="To Delete",
            url="https://example.com/delete",
            events=["lead.created"],
            created_by_id=test_user.id,
        )
        db_session.add(webhook)
        await db_session.commit()
        await db_session.refresh(webhook)
        webhook_id = webhook.id

        response = await client.delete(
            f"/api/webhooks/{webhook_id}",
            headers=auth_headers,
        )
        assert response.status_code == 204

        result = await db_session.execute(
            select(Webhook).where(Webhook.id == webhook_id)
        )
        assert result.scalar_one_or_none() is None


class TestWebhookDeliveries:
    """Tests for webhook delivery logging."""

    @pytest.mark.asyncio
    async def test_get_deliveries_empty(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_webhook: Webhook,
    ):
        """Test getting deliveries when none exist."""
        response = await client.get(
            f"/api/webhooks/{test_webhook.id}/deliveries",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data == []

    @pytest.mark.asyncio
    async def test_get_deliveries_with_data(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_webhook: Webhook,
    ):
        """Test getting deliveries with data."""
        delivery = WebhookDelivery(
            webhook_id=test_webhook.id,
            event_type="lead.created",
            payload={"id": 1, "name": "Test Lead"},
            status="success",
            response_code=200,
        )
        db_session.add(delivery)
        await db_session.commit()

        response = await client.get(
            f"/api/webhooks/{test_webhook.id}/deliveries",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["status"] == "success"
        assert data[0]["event_type"] == "lead.created"
        assert data[0]["response_code"] == 200


class TestWebhookSignature:
    """Tests for HMAC-SHA256 webhook signature computation."""

    def test_compute_signature(self):
        """Test that compute_signature produces correct HMAC-SHA256."""
        payload = b'{"event": "lead.created", "data": {"id": 1}}'
        secret = "test-secret"

        result = compute_signature(payload, secret)

        expected = hmac.new(
            secret.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()

        assert result == expected

    def test_compute_signature_different_secrets(self):
        """Test that different secrets produce different signatures."""
        payload = b'{"event": "test"}'

        sig1 = compute_signature(payload, "secret1")
        sig2 = compute_signature(payload, "secret2")

        assert sig1 != sig2

    def test_compute_signature_different_payloads(self):
        """Test that different payloads produce different signatures."""
        secret = "same-secret"

        sig1 = compute_signature(b'{"a": 1}', secret)
        sig2 = compute_signature(b'{"a": 2}', secret)

        assert sig1 != sig2


class TestEventSystem:
    """Tests for the event emitter system."""

    @pytest.mark.asyncio
    async def test_emit_calls_handler(self):
        """Test that emit calls registered handler."""
        clear_handlers()
        received = []

        async def handler(event_type, payload):
            received.append((event_type, payload))

        on("test.event", handler)
        await emit("test.event", {"key": "value"})

        assert len(received) == 1
        assert received[0][0] == "test.event"
        assert received[0][1] == {"key": "value"}

        clear_handlers()

    @pytest.mark.asyncio
    async def test_emit_multiple_handlers(self):
        """Test that emit calls all registered handlers."""
        clear_handlers()
        results = []

        async def handler1(event_type, payload):
            results.append("handler1")

        async def handler2(event_type, payload):
            results.append("handler2")

        on("test.event", handler1)
        on("test.event", handler2)
        await emit("test.event", {})

        assert len(results) == 2
        assert "handler1" in results
        assert "handler2" in results

        clear_handlers()

    @pytest.mark.asyncio
    async def test_emit_no_handlers(self):
        """Test that emit with no handlers does not error."""
        clear_handlers()
        await emit("no.handlers", {"data": "test"})
        # Should not raise

    @pytest.mark.asyncio
    async def test_handler_error_does_not_stop_others(self):
        """Test that a failing handler does not prevent other handlers from running."""
        clear_handlers()
        results = []

        async def failing_handler(event_type, payload):
            raise ValueError("Handler error")

        async def working_handler(event_type, payload):
            results.append("success")

        on("test.event", failing_handler)
        on("test.event", working_handler)
        await emit("test.event", {})

        assert len(results) == 1
        assert results[0] == "success"

        clear_handlers()

    @pytest.mark.asyncio
    async def test_off_removes_handler(self):
        """Test that off removes a handler."""
        clear_handlers()
        results = []

        async def handler(event_type, payload):
            results.append("called")

        on("test.event", handler)
        off("test.event", handler)
        await emit("test.event", {})

        assert len(results) == 0

        clear_handlers()

    def test_get_handlers(self):
        """Test that get_handlers returns registered handlers."""
        clear_handlers()

        async def handler(event_type, payload):
            pass

        on("test.event", handler)
        handlers = get_handlers("test.event")
        assert len(handlers) == 1
        assert handlers[0] is handler

        clear_handlers()


class TestWebhooksUnauthorized:
    """Tests for unauthorized access."""

    @pytest.mark.asyncio
    async def test_create_webhook_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        response = await client.post(
            "/api/webhooks",
            json={"name": "Test", "url": "https://example.com", "events": ["lead.created"]},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_list_webhooks_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        response = await client.get("/api/webhooks")
        assert response.status_code == 401
