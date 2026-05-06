"""Tests for attachment plumbing and Gmail from-name resolution.

Covers the two gaps closed in ``esign-email-fixes``:
  1. ``attach_pdf=True`` on quote/proposal sends now reaches the
     provider as a real ``application/pdf`` attachment.
  2. The Gmail ``From`` header uses the sender's ``User.full_name``
     instead of the email local-part.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.email.service import EmailService, _resolve_from_name, _try_gmail_send
from src.email.models import EmailQueue
from src.integrations.gmail.models import GmailConnection
from src.integrations.gmail.sender import EmailAttachment, build_rfc822


class TestBuildRfc822Attachments:
    """RFC-822 builder threads attachment bytes through as MIME parts."""

    def test_pdf_attachment_appears_in_raw_message(self):
        raw = build_rfc822(
            to="customer@example.com",
            subject="Quote QT-2026-0001",
            body_html="<p>Review your quote.</p>",
            body_text="Review your quote.",
            from_email="sales@example.com",
            from_name="Harsh Varma",
            attachments=[EmailAttachment(
                filename="quote-QT-2026-0001.pdf",
                content=b"%PDF-1.4\ntest",
                content_type="application/pdf",
            )],
        )

        decoded = raw.decode("utf-8", errors="replace")
        assert "Content-Type: application/pdf" in decoded
        assert "filename=\"quote-QT-2026-0001.pdf\"" in decoded
        assert "From: Harsh Varma <sales@example.com>" in decoded

    def test_no_attachments_produces_plain_multipart(self):
        raw = build_rfc822(
            to="customer@example.com",
            subject="Hello",
            body_html="<p>Hi</p>",
            body_text="Hi",
            from_email="sales@example.com",
            from_name="Sales",
        )
        decoded = raw.decode("utf-8", errors="replace")
        assert "Content-Type: application/pdf" not in decoded


class TestResolveFromName:
    """Prefer the user's full name over the Gmail local-part."""

    @pytest.mark.asyncio
    async def test_uses_user_full_name(self, db_session: AsyncSession, test_user: User):
        name = await _resolve_from_name(db_session, test_user.id, "local@midwestsystemsolutions.com")
        assert name == test_user.full_name

    @pytest.mark.asyncio
    async def test_falls_back_to_local_part_when_no_name_anywhere(self, db_session: AsyncSession):
        empty_branding = {"email_from_name": ""}
        with patch(
            "src.email.service.TenantBrandingHelper.get_branding_for_user",
            AsyncMock(return_value=empty_branding),
        ):
            name = await _resolve_from_name(db_session, 999_999, "harsh@midwestsystemsolutions.com")
        assert name == "harsh"


class TestGmailSendWithAttachment:
    """End-to-end: _try_gmail_send passes attachments into build_rfc822."""

    @pytest.mark.asyncio
    async def test_attachment_flows_to_gmail_send(
        self, db_session: AsyncSession, test_user: User,
    ):
        conn = GmailConnection(
            user_id=test_user.id,
            email="harsh@midwestsystemsolutions.com",
            access_token="tok",
            refresh_token="rt",
            token_expiry=datetime(2099, 1, 1, tzinfo=UTC),
            scopes="gmail.send",
        )
        db_session.add(conn)
        await db_session.flush()

        email = EmailQueue(
            to_email="customer@example.com",
            subject="Quote QT-2026-0001",
            body="<p>Your quote</p>",
            sent_by_id=test_user.id,
            entity_type="quotes",
            entity_id=42,
            status="pending",
        )
        db_session.add(email)
        await db_session.flush()

        attachments = [EmailAttachment(
            filename="quote-QT-2026-0001.pdf",
            content=b"%PDF-1.4 bytes",
            content_type="application/pdf",
        )]

        mock_send = AsyncMock(return_value={"id": "gmail-msg-id", "threadId": "gmail-thread-id"})
        with patch("src.integrations.gmail.client.GmailClient.send_message", mock_send), \
             patch("src.integrations.gmail.client.GmailClient._refresh_if_needed", AsyncMock()):
            ok = await _try_gmail_send(email, db_session, attachments=attachments)

        assert ok is True
        assert email.sent_via == "gmail"
        # Since PR #197, message_id is the locally-generated RFC value that
        # the message envelope actually carries, not Gmail's internal numeric
        # id, so sync dedup can match exactly. Just assert it's a non-empty
        # RFC-shaped string ending in the sender's domain.
        assert email.message_id and email.message_id.startswith("<")
        assert "@midwestsystemsolutions.com>" in email.message_id
        assert email.thread_id == "gmail-thread-id"

        raw_bytes = mock_send.await_args.args[0]
        decoded = raw_bytes.decode("utf-8", errors="replace")
        assert "Content-Type: application/pdf" in decoded
        assert "quote-QT-2026-0001.pdf" in decoded
        # From-name should be User.full_name, not the email local-part.
        assert f"From: {test_user.full_name} <harsh@midwestsystemsolutions.com>" in decoded


class TestQueueEmailAttachmentsPassthrough:
    """queue_email forwards attachments into _attempt_send."""

    @pytest.mark.asyncio
    async def test_attachments_forwarded_to_attempt_send(
        self, db_session: AsyncSession, test_user: User,
    ):
        service = EmailService(db_session)
        attachments = [EmailAttachment(
            filename="x.pdf", content=b"abc", content_type="application/pdf",
        )]

        with patch.object(service, "_attempt_send", AsyncMock()) as mock_attempt:
            await service.queue_email(
                to_email="customer@example.com",
                subject="hi",
                body="<p>hi</p>",
                sent_by_id=test_user.id,
                attachments=attachments,
            )

        mock_attempt.assert_awaited_once()
        kwargs = mock_attempt.await_args.kwargs
        assert kwargs["attachments"] is attachments
