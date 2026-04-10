"""
Unit tests for inbound email endpoints and email thread functionality.

Tests for:
- Inbound webhook processing (store InboundEmail, auto-match contact)
- Email thread endpoint (unified inbound + outbound chronological view)
- Enhanced email sending with cc/bcc fields
"""

import pytest
import json
import time
import base64
import hashlib
import hmac as hmac_mod
from datetime import datetime, timezone
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.auth.models import User
from src.contacts.models import Contact
from src.email.models import EmailQueue, InboundEmail

# Real svix-compatible signing for webhook tests (no mocking)
_WEBHOOK_SECRET = "whsec_dGVzdHNlY3JldGZvcnRlc3Rpbmc="  # base64("testsecretfortesting")
_MSG_COUNTER = 0


def _svix_headers(payload: dict) -> dict:
    """Generate valid svix webhook headers for a JSON payload."""
    global _MSG_COUNTER
    _MSG_COUNTER += 1
    msg_id = f"msg_test_{_MSG_COUNTER}"
    timestamp = str(int(time.time()))
    body = json.dumps(payload).encode()
    secret_bytes = base64.b64decode(_WEBHOOK_SECRET.removeprefix("whsec_"))
    to_sign = f"{msg_id}.{timestamp}.".encode() + body
    sig = base64.b64encode(
        hmac_mod.new(secret_bytes, to_sign, hashlib.sha256).digest()
    ).decode()
    return {
        "svix-id": msg_id,
        "svix-timestamp": timestamp,
        "svix-signature": f"v1,{sig}",
    }


class TestInboundWebhook:
    """Tests for the inbound email webhook endpoint."""

    @pytest.fixture(autouse=True)
    def _set_webhook_secret(self, monkeypatch):
        """Set the Resend webhook secret so the endpoint doesn't return 503."""
        from src.config import settings
        monkeypatch.setattr(settings, "RESEND_WEBHOOK_SECRET", _WEBHOOK_SECRET)

    @pytest.mark.asyncio
    async def test_inbound_webhook_stores_email(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_contact: Contact,
    ):
        """Should store an inbound email from webhook payload."""
        payload = {
            "type": "email.received",
            "data": {
                "id": "resend-email-001",
                "from": test_contact.email,
                "to": ["crm@example.com"],
                "subject": "Follow up on proposal",
                "text": "Hi, I wanted to follow up on the proposal.",
                "html": "<p>Hi, I wanted to follow up on the proposal.</p>",
            },
        }

        response = await client.post(
            "/api/email/inbound-webhook",
            json=payload,
            headers=_svix_headers(payload),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "processed"
        assert "inbound_email_id" in data

        # Verify the email was stored
        result = await db_session.execute(
            select(InboundEmail).where(InboundEmail.resend_email_id == "resend-email-001")
        )
        inbound = result.scalar_one()
        assert inbound.from_email == test_contact.email
        assert inbound.to_email == "crm@example.com"
        assert inbound.subject == "Follow up on proposal"
        assert inbound.body_text == "Hi, I wanted to follow up on the proposal."
        assert inbound.body_html == "<p>Hi, I wanted to follow up on the proposal.</p>"

    @pytest.mark.asyncio
    async def test_inbound_webhook_auto_matches_contact(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_contact: Contact,
    ):
        """Should auto-match inbound email to existing contact by from_email."""
        payload = {
            "type": "email.received",
            "data": {
                "id": "resend-email-002",
                "from": test_contact.email,
                "to": ["crm@example.com"],
                "subject": "Test auto-match",
                "text": "This should match a contact.",
            },
        }

        response = await client.post(
            "/api/email/inbound-webhook",
            json=payload,
            headers=_svix_headers(payload),
        )
        assert response.status_code == 200

        result = await db_session.execute(
            select(InboundEmail).where(InboundEmail.resend_email_id == "resend-email-002")
        )
        inbound = result.scalar_one()
        assert inbound.entity_type == "contacts"
        assert inbound.entity_id == test_contact.id

    @pytest.mark.asyncio
    async def test_inbound_webhook_logs_activity_on_matched_contact(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_contact: Contact,
    ):
        """Should log an activity on the matched contact."""
        from src.activities.models import Activity

        payload = {
            "type": "email.received",
            "data": {
                "id": "resend-email-003",
                "from": test_contact.email,
                "to": ["crm@example.com"],
                "subject": "Activity test email",
                "text": "Should create an activity.",
            },
        }

        response = await client.post(
            "/api/email/inbound-webhook",
            json=payload,
            headers=_svix_headers(payload),
        )
        assert response.status_code == 200

        result = await db_session.execute(
            select(Activity).where(
                Activity.entity_type == "contacts",
                Activity.entity_id == test_contact.id,
                Activity.activity_type == "email",
            )
        )
        activities = list(result.scalars().all())
        email_activities = [a for a in activities if "Inbound email:" in a.subject]
        assert len(email_activities) >= 1
        assert "Activity test email" in email_activities[0].subject

    @pytest.mark.asyncio
    async def test_inbound_webhook_no_contact_match(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Should store inbound email without entity link when no contact matches."""
        payload = {
            "type": "email.received",
            "data": {
                "id": "resend-email-004",
                "from": "unknown@nowhere.com",
                "to": ["crm@example.com"],
                "subject": "From unknown sender",
                "text": "No contact match expected.",
            },
        }

        response = await client.post(
            "/api/email/inbound-webhook",
            json=payload,
            headers=_svix_headers(payload),
        )
        assert response.status_code == 200

        result = await db_session.execute(
            select(InboundEmail).where(InboundEmail.resend_email_id == "resend-email-004")
        )
        inbound = result.scalar_one()
        assert inbound.entity_type is None
        assert inbound.entity_id is None

    @pytest.mark.asyncio
    async def test_inbound_webhook_ignores_non_email_received_events(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Should ignore webhook events that are not email.received."""
        payload = {
            "type": "email.delivered",
            "data": {"id": "resend-email-005"},
        }

        response = await client.post(
            "/api/email/inbound-webhook",
            json=payload,
            headers=_svix_headers(payload),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ignored"

    @pytest.mark.asyncio
    async def test_inbound_webhook_handles_cc(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Should store CC addresses from inbound webhook."""
        payload = {
            "type": "email.received",
            "data": {
                "id": "resend-email-006",
                "from": "sender@example.com",
                "to": ["crm@example.com"],
                "cc": ["cc1@example.com", "cc2@example.com"],
                "subject": "CC test",
                "text": "Email with CC.",
            },
        }

        response = await client.post(
            "/api/email/inbound-webhook",
            json=payload,
            headers=_svix_headers(payload),
        )
        assert response.status_code == 200

        result = await db_session.execute(
            select(InboundEmail).where(InboundEmail.resend_email_id == "resend-email-006")
        )
        inbound = result.scalar_one()
        assert "cc1@example.com" in inbound.cc
        assert "cc2@example.com" in inbound.cc


class TestEmailThread:
    """Tests for the email thread endpoint."""

    @pytest.mark.asyncio
    async def test_thread_returns_both_inbound_and_outbound(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_contact: Contact,
    ):
        """Should return both inbound and outbound emails in chronological order."""
        # Create outbound email
        outbound = EmailQueue(
            to_email=test_contact.email,
            subject="Outbound test",
            body="<p>Outbound body</p>",
            status="sent",
            entity_type="contacts",
            entity_id=test_contact.id,
            sent_by_id=test_user.id,
        )
        db_session.add(outbound)

        # Create inbound email
        inbound = InboundEmail(
            resend_email_id="thread-test-001",
            from_email=test_contact.email,
            to_email="crm@example.com",
            subject="Inbound test",
            body_text="Inbound body text",
            body_html="<p>Inbound body</p>",
            entity_type="contacts",
            entity_id=test_contact.id,
            received_at=datetime.now(timezone.utc),
        )
        db_session.add(inbound)
        await db_session.commit()

        response = await client.get(
            "/api/email/thread",
            headers=auth_headers,
            params={"entity_type": "contacts", "entity_id": test_contact.id},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        directions = {item["direction"] for item in data["items"]}
        assert "inbound" in directions
        assert "outbound" in directions

    @pytest.mark.asyncio
    async def test_thread_pagination(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_contact: Contact,
    ):
        """Should paginate thread results correctly."""
        # Create 5 outbound emails
        for i in range(5):
            email = EmailQueue(
                to_email=test_contact.email,
                subject=f"Outbound {i}",
                body=f"<p>Body {i}</p>",
                status="sent",
                entity_type="contacts",
                entity_id=test_contact.id,
                sent_by_id=test_user.id,
            )
            db_session.add(email)
        await db_session.commit()

        response = await client.get(
            "/api/email/thread",
            headers=auth_headers,
            params={
                "entity_type": "contacts",
                "entity_id": test_contact.id,
                "page": 1,
                "page_size": 3,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 5
        assert len(data["items"]) == 3
        assert data["pages"] == 2

    @pytest.mark.asyncio
    async def test_thread_empty(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contact: Contact,
    ):
        """Should return empty thread when no emails exist for entity."""
        response = await client.get(
            "/api/email/thread",
            headers=auth_headers,
            params={"entity_type": "contacts", "entity_id": test_contact.id},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["items"] == []

    @pytest.mark.asyncio
    async def test_thread_requires_auth(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Should require authentication to access thread endpoint."""
        response = await client.get(
            "/api/email/thread",
            params={"entity_type": "contacts", "entity_id": 1},
        )
        assert response.status_code == 401


class TestEnhancedEmailSending:
    """Tests for enhanced email sending with cc/bcc fields."""

    @pytest.mark.asyncio
    async def test_send_email_with_cc_bcc(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contact: Contact,
    ):
        """Should store cc and bcc fields when sending email."""
        response = await client.post(
            "/api/email/send",
            headers=auth_headers,
            json={
                "to_email": "recipient@example.com",
                "subject": "CC/BCC Test",
                "body": "<p>Test with CC and BCC</p>",
                "cc": "cc@example.com",
                "bcc": "bcc@example.com",
                "entity_type": "contacts",
                "entity_id": test_contact.id,
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["cc"] == "cc@example.com"
        assert data["bcc"] == "bcc@example.com"

    @pytest.mark.asyncio
    async def test_send_email_with_from_email(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Should store custom from_email when sending email."""
        response = await client.post(
            "/api/email/send",
            headers=auth_headers,
            json={
                "to_email": "recipient@example.com",
                "subject": "Custom From Test",
                "body": "<p>Test with custom from</p>",
                "from_email": "custom@resend.dev",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["from_email"] == "custom@resend.dev"

    @pytest.mark.asyncio
    async def test_send_email_without_cc_bcc(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Should work without cc/bcc fields (backward compatibility)."""
        response = await client.post(
            "/api/email/send",
            headers=auth_headers,
            json={
                "to_email": "recipient@example.com",
                "subject": "No CC Test",
                "body": "<p>No CC or BCC</p>",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["cc"] is None
        assert data["bcc"] is None
