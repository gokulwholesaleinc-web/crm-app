"""
Unit tests for email endpoints.

Tests for sending emails, template emails, email tracking (open pixel, click redirect),
and email queue status listing.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.auth.models import User
from src.contacts.models import Contact
from src.email.models import EmailQueue
from src.campaigns.models import EmailTemplate


class TestSendEmail:
    """Tests for the send email endpoint."""

    @pytest.mark.asyncio
    async def test_send_email_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contact: Contact,
    ):
        """Test sending a basic email creates a queue entry."""
        response = await client.post(
            "/api/email/send",
            headers=auth_headers,
            json={
                "to_email": "recipient@example.com",
                "subject": "Test Subject",
                "body": "<p>Hello World</p>",
                "entity_type": "contacts",
                "entity_id": test_contact.id,
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["to_email"] == "recipient@example.com"
        assert data["subject"] == "Test Subject"
        assert data["body"] == "<p>Hello World</p>"
        assert data["entity_type"] == "contacts"
        assert data["entity_id"] == test_contact.id
        assert "id" in data
        # Status will be either pending, sent, or failed depending on SMTP config
        assert data["status"] in ("pending", "sent", "failed")
        assert data["open_count"] == 0
        assert data["click_count"] == 0

    @pytest.mark.asyncio
    async def test_send_email_without_entity(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test sending email without linking to an entity."""
        response = await client.post(
            "/api/email/send",
            headers=auth_headers,
            json={
                "to_email": "standalone@example.com",
                "subject": "Standalone Email",
                "body": "<p>No entity link</p>",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["entity_type"] is None
        assert data["entity_id"] is None

    @pytest.mark.asyncio
    async def test_send_email_unauthorized(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Test sending email without auth returns 401."""
        response = await client.post(
            "/api/email/send",
            json={
                "to_email": "test@example.com",
                "subject": "Test",
                "body": "Body",
            },
        )

        assert response.status_code == 401


class TestSendTemplateEmail:
    """Tests for template-based email sending."""

    @pytest.mark.asyncio
    async def test_send_template_email_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Test sending an email using a template."""
        # Create a template
        template = EmailTemplate(
            name="Welcome Template",
            subject_template="Welcome {{name}}",
            body_template="<p>Hello {{name}}, welcome to our platform!</p>",
        )
        db_session.add(template)
        await db_session.commit()
        await db_session.refresh(template)

        response = await client.post(
            "/api/email/send-template",
            headers=auth_headers,
            json={
                "to_email": "newuser@example.com",
                "template_id": template.id,
                "variables": {"name": "John"},
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["to_email"] == "newuser@example.com"
        assert "John" in data["subject"]
        assert "John" in data["body"]
        assert data["template_id"] == template.id

    @pytest.mark.asyncio
    async def test_send_template_email_not_found(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test sending template email with non-existent template returns 404."""
        response = await client.post(
            "/api/email/send-template",
            headers=auth_headers,
            json={
                "to_email": "test@example.com",
                "template_id": 99999,
                "variables": {},
            },
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_send_template_email_unauthorized(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Test sending template email without auth returns 401."""
        response = await client.post(
            "/api/email/send-template",
            json={
                "to_email": "test@example.com",
                "template_id": 1,
                "variables": {},
            },
        )

        assert response.status_code == 401


class TestEmailTracking:
    """Tests for email open and click tracking."""

    @pytest.mark.asyncio
    async def test_track_email_open(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test tracking pixel records an email open event."""
        # Create an email queue entry
        email = EmailQueue(
            to_email="tracked@example.com",
            subject="Tracked Email",
            body="<p>Tracked</p>",
            status="sent",
            sent_by_id=test_user.id,
        )
        db_session.add(email)
        await db_session.commit()
        await db_session.refresh(email)

        # Hit the tracking pixel (no auth required)
        response = await client.get(
            f"/api/email/track/{email.id}/open",
        )

        assert response.status_code == 200
        assert response.headers["content-type"] == "image/gif"

        # Verify open was recorded
        await db_session.refresh(email)
        assert email.open_count >= 1
        assert email.opened_at is not None

    @pytest.mark.asyncio
    async def test_track_email_open_increments_count(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test that multiple opens increment the count."""
        email = EmailQueue(
            to_email="multiopen@example.com",
            subject="Multi Open Email",
            body="<p>Open me</p>",
            status="sent",
            sent_by_id=test_user.id,
        )
        db_session.add(email)
        await db_session.commit()
        await db_session.refresh(email)

        # Open twice
        await client.get(f"/api/email/track/{email.id}/open")
        await client.get(f"/api/email/track/{email.id}/open")

        await db_session.refresh(email)
        assert email.open_count >= 2

    @pytest.mark.asyncio
    async def test_track_email_click(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test click tracking records event and redirects."""
        email = EmailQueue(
            to_email="clicked@example.com",
            subject="Click Email",
            body="<p>Click me</p>",
            status="sent",
            sent_by_id=test_user.id,
        )
        db_session.add(email)
        await db_session.commit()
        await db_session.refresh(email)

        # Hit the click tracker (no auth required)
        response = await client.get(
            f"/api/email/track/{email.id}/click",
            params={"url": "https://example.com/landing"},
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.headers["location"] == "https://example.com/landing"

        # Verify click was recorded
        await db_session.refresh(email)
        assert email.click_count >= 1
        assert email.clicked_at is not None


class TestEmailList:
    """Tests for email listing endpoint."""

    @pytest.mark.asyncio
    async def test_list_emails_empty(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test listing emails when none exist."""
        response = await client.get(
            "/api/email",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["page"] == 1

    @pytest.mark.asyncio
    async def test_list_emails_with_data(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Test listing emails returns existing queue entries."""
        email = EmailQueue(
            to_email="listed@example.com",
            subject="Listed Email",
            body="<p>In the list</p>",
            status="pending",
            sent_by_id=test_user.id,
        )
        db_session.add(email)
        await db_session.commit()

        response = await client.get(
            "/api/email",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1

    @pytest.mark.asyncio
    async def test_list_emails_filter_by_status(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Test filtering emails by status."""
        email = EmailQueue(
            to_email="failed@example.com",
            subject="Failed Email",
            body="<p>Failed</p>",
            status="failed",
            error="SMTP connection refused",
            sent_by_id=test_user.id,
        )
        db_session.add(email)
        await db_session.commit()

        response = await client.get(
            "/api/email",
            headers=auth_headers,
            params={"status": "failed"},
        )

        assert response.status_code == 200
        data = response.json()
        assert all(item["status"] == "failed" for item in data["items"])

    @pytest.mark.asyncio
    async def test_list_emails_pagination(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Test email list pagination."""
        for i in range(15):
            email = EmailQueue(
                to_email=f"page{i}@example.com",
                subject=f"Email {i}",
                body=f"<p>Body {i}</p>",
                status="pending",
                sent_by_id=test_user.id,
            )
            db_session.add(email)
        await db_session.commit()

        response = await client.get(
            "/api/email",
            headers=auth_headers,
            params={"page": 1, "page_size": 10},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 10
        assert data["total"] == 15

    @pytest.mark.asyncio
    async def test_list_emails_unauthorized(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Test listing emails without auth returns 401."""
        response = await client.get("/api/email")
        assert response.status_code == 401


class TestGetEmail:
    """Tests for get email by ID."""

    @pytest.mark.asyncio
    async def test_get_email_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Test getting a specific email by ID."""
        email = EmailQueue(
            to_email="specific@example.com",
            subject="Specific Email",
            body="<p>Specific</p>",
            status="pending",
            sent_by_id=test_user.id,
        )
        db_session.add(email)
        await db_session.commit()
        await db_session.refresh(email)

        response = await client.get(
            f"/api/email/{email.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == email.id
        assert data["to_email"] == "specific@example.com"

    @pytest.mark.asyncio
    async def test_get_email_not_found(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test getting non-existent email returns 404."""
        response = await client.get(
            "/api/email/99999",
            headers=auth_headers,
        )

        assert response.status_code == 404
