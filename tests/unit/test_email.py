"""Tests for email sending API endpoints."""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.email.models import EmailQueue
from src.email.service import render_template


class TestRenderTemplate:
    """Tests for template rendering."""

    def test_render_simple(self):
        result = render_template("Hello {{name}}", {"name": "World"})
        assert result == "Hello World"

    def test_render_multiple_vars(self):
        result = render_template(
            "Hi {{first}} {{last}}", {"first": "John", "last": "Doe"}
        )
        assert result == "Hi John Doe"

    def test_render_no_vars(self):
        result = render_template("No vars here", {})
        assert result == "No vars here"

    def test_render_missing_var(self):
        result = render_template("Hello {{name}}", {})
        assert result == "Hello {{name}}"


class TestSendEmail:
    """Tests for POST /api/email/send."""

    @pytest.mark.asyncio
    async def test_send_email_creates_queue_entry(
        self, client: AsyncClient, auth_headers: dict
    ):
        response = await client.post(
            "/api/email/send",
            json={
                "to_email": "test@example.com",
                "subject": "Test Subject",
                "body": "<p>Hello</p>",
            },
            headers=auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["to_email"] == "test@example.com"
        assert data["subject"] == "Test Subject"
        assert data["body"] == "<p>Hello</p>"
        assert data["status"] in ("sent", "failed")
        assert data["attempts"] == 1

    @pytest.mark.asyncio
    async def test_send_email_with_entity(
        self, client: AsyncClient, auth_headers: dict, test_contact
    ):
        response = await client.post(
            "/api/email/send",
            json={
                "to_email": "test@example.com",
                "subject": "Follow up",
                "body": "Body text",
                "entity_type": "contacts",
                "entity_id": test_contact.id,
            },
            headers=auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["entity_type"] == "contacts"
        assert data["entity_id"] == test_contact.id

    @pytest.mark.asyncio
    async def test_send_email_requires_auth(self, client: AsyncClient):
        response = await client.post(
            "/api/email/send",
            json={
                "to_email": "test@example.com",
                "subject": "Test",
                "body": "Body",
            },
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_send_email_validates_email(
        self, client: AsyncClient, auth_headers: dict
    ):
        response = await client.post(
            "/api/email/send",
            json={
                "to_email": "not-an-email",
                "subject": "Test",
                "body": "Body",
            },
            headers=auth_headers,
        )
        assert response.status_code == 422


class TestListEmails:
    """Tests for GET /api/email."""

    @pytest.mark.asyncio
    async def test_list_emails_empty(
        self, client: AsyncClient, auth_headers: dict
    ):
        response = await client.get("/api/email", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_list_emails_after_send(
        self, client: AsyncClient, auth_headers: dict
    ):
        await client.post(
            "/api/email/send",
            json={
                "to_email": "a@example.com",
                "subject": "S1",
                "body": "B1",
            },
            headers=auth_headers,
        )
        response = await client.get("/api/email", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1

    @pytest.mark.asyncio
    async def test_list_emails_filter_by_entity(
        self, client: AsyncClient, auth_headers: dict, test_contact
    ):
        await client.post(
            "/api/email/send",
            json={
                "to_email": "a@example.com",
                "subject": "S1",
                "body": "B1",
                "entity_type": "contacts",
                "entity_id": test_contact.id,
            },
            headers=auth_headers,
        )
        await client.post(
            "/api/email/send",
            json={
                "to_email": "b@example.com",
                "subject": "S2",
                "body": "B2",
            },
            headers=auth_headers,
        )
        response = await client.get(
            "/api/email",
            params={"entity_type": "contacts", "entity_id": test_contact.id},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1

    @pytest.mark.asyncio
    async def test_list_emails_requires_auth(self, client: AsyncClient):
        response = await client.get("/api/email")
        assert response.status_code == 401


class TestGetEmail:
    """Tests for GET /api/email/{id}."""

    @pytest.mark.asyncio
    async def test_get_email_by_id(
        self, client: AsyncClient, auth_headers: dict
    ):
        send_resp = await client.post(
            "/api/email/send",
            json={
                "to_email": "x@example.com",
                "subject": "Get test",
                "body": "Body",
            },
            headers=auth_headers,
        )
        email_id = send_resp.json()["id"]

        response = await client.get(
            f"/api/email/{email_id}", headers=auth_headers
        )
        assert response.status_code == 200
        assert response.json()["id"] == email_id

    @pytest.mark.asyncio
    async def test_get_email_not_found(
        self, client: AsyncClient, auth_headers: dict
    ):
        response = await client.get("/api/email/99999", headers=auth_headers)
        assert response.status_code == 404


class TestEmailTracking:
    """Tests for email open/click tracking endpoints."""

    @pytest.mark.asyncio
    async def test_track_open_returns_pixel(
        self, client: AsyncClient, auth_headers: dict
    ):
        send_resp = await client.post(
            "/api/email/send",
            json={
                "to_email": "x@example.com",
                "subject": "Track test",
                "body": "Body",
            },
            headers=auth_headers,
        )
        email_id = send_resp.json()["id"]

        response = await client.get(f"/api/email/track/{email_id}/open")
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/gif"

    @pytest.mark.asyncio
    async def test_track_open_increments_count(
        self, client: AsyncClient, auth_headers: dict
    ):
        send_resp = await client.post(
            "/api/email/send",
            json={
                "to_email": "x@example.com",
                "subject": "Track test",
                "body": "Body",
            },
            headers=auth_headers,
        )
        email_id = send_resp.json()["id"]

        await client.get(f"/api/email/track/{email_id}/open")
        await client.get(f"/api/email/track/{email_id}/open")

        detail = await client.get(
            f"/api/email/{email_id}", headers=auth_headers
        )
        assert detail.json()["open_count"] == 2
        assert detail.json()["opened_at"] is not None

    @pytest.mark.asyncio
    async def test_track_click_redirects(
        self, client: AsyncClient, auth_headers: dict
    ):
        send_resp = await client.post(
            "/api/email/send",
            json={
                "to_email": "x@example.com",
                "subject": "Track test",
                "body": "Body",
            },
            headers=auth_headers,
        )
        email_id = send_resp.json()["id"]

        response = await client.get(
            f"/api/email/track/{email_id}/click",
            params={"url": "https://example.com"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "https://example.com"

    @pytest.mark.asyncio
    async def test_track_click_increments_count(
        self, client: AsyncClient, auth_headers: dict
    ):
        send_resp = await client.post(
            "/api/email/send",
            json={
                "to_email": "x@example.com",
                "subject": "Track test",
                "body": "Body",
            },
            headers=auth_headers,
        )
        email_id = send_resp.json()["id"]

        await client.get(
            f"/api/email/track/{email_id}/click",
            params={"url": "https://example.com"},
            follow_redirects=False,
        )

        detail = await client.get(
            f"/api/email/{email_id}", headers=auth_headers
        )
        assert detail.json()["click_count"] == 1
        assert detail.json()["clicked_at"] is not None
