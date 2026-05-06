"""
Unit tests for email thread + enhanced email sending.

The inbound Resend webhook tests were removed when Resend was retired
in favour of the Gmail-only outbound path; inbound mail is now ingested
through the per-user Gmail history poller (src.integrations.gmail.sync).
"""

import pytest
from datetime import datetime, timezone
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.auth.models import User
from src.contacts.models import Contact
from src.email.models import EmailQueue, InboundEmail


async def _make_admin(db_session: AsyncSession, user: User) -> None:
    """Promote the test viewer to admin so the participant filter bypass
    fires; the SQLite test path otherwise degrades to composer-only and
    inbound rows that aren't anchored to ``sent_by_id`` would be hidden."""
    user.is_superuser = True
    db_session.add(user)
    await db_session.commit()


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
        await _make_admin(db_session, test_user)

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
    async def test_thread_includes_thread_id(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_contact: Contact,
    ):
        """Thread response must expose thread_id on both inbound and outbound rows.

        The EmailThread UI groups bubbles by this field; if it's missing,
        every message renders as a standalone thread.
        """
        await _make_admin(db_session, test_user)
        outbound = EmailQueue(
            to_email=test_contact.email,
            subject="Initial",
            body="<p>Hi</p>",
            status="sent",
            entity_type="contacts",
            entity_id=test_contact.id,
            sent_by_id=test_user.id,
            thread_id="gmail-thread-42",
        )
        db_session.add(outbound)
        inbound = InboundEmail(
            resend_email_id="gmail:reply-1",
            from_email=test_contact.email,
            to_email="crm@example.com",
            subject="Re: Initial",
            body_text="Thanks",
            entity_type="contacts",
            entity_id=test_contact.id,
            received_at=datetime.now(timezone.utc),
            thread_id="gmail-thread-42",
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
        thread_ids = {item.get("thread_id") for item in data["items"]}
        assert thread_ids == {"gmail-thread-42"}

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
                "from_email": "custom@example.com",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["from_email"] == "custom@example.com"

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
