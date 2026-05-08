"""Integration tests for the inbound-reply notification hook in _store_inbound.

Calls _store_inbound directly — no Gmail API mocking needed.
No mocks on any business logic. SQLite in-memory DB via conftest fixtures.
"""

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.account.models import UserNotificationPrefs
from src.contacts.models import Contact
from src.email.models import EmailQueue, InboundEmail
from src.integrations.gmail.models import GmailConnection
from src.integrations.gmail.sync import _store_inbound
from src.notifications.models import Notification


def _make_msg(
    *,
    from_: str,
    to: str,
    message_id: str = "<msg-001@example.com>",
    thread_id: str = "thread-001",
    in_reply_to: str | None = None,
    subject: str = "Re: Project Update",
    body_text: str = "Thanks for the update!",
    raw_id: str = "gmailid001",
) -> dict:
    """Build a minimal msg dict matching the shape that GmailClient.get_message produces."""
    return {
        "from": from_,
        "to": to,
        "message_id": message_id,
        "thread_id": thread_id,
        "in_reply_to": in_reply_to,
        "subject": subject,
        "body_text": body_text,
        "body_html": None,
        "date": datetime.now(timezone.utc),
        "to_list": [to],
        "cc_list": [],
        "bcc_list": [],
        "cc": None,
        "bcc": None,
        "attachments": None,
        "raw_payload": {"id": raw_id},
    }


@pytest_asyncio.fixture
async def gmail_connection(db_session: AsyncSession, test_user) -> GmailConnection:
    conn = GmailConnection(
        user_id=test_user.id,
        email="owner@company.com",
        access_token="tok",
        refresh_token="rtok",
        token_expiry=datetime(2099, 1, 1, tzinfo=timezone.utc),
        scopes="https://mail.google.com/",
    )
    db_session.add(conn)
    await db_session.flush()
    return conn


@pytest_asyncio.fixture
async def owned_contact(db_session: AsyncSession, test_user) -> Contact:
    c = Contact(
        email="sender@client.com",
        first_name="Jane",
        last_name="Client",
        owner_id=test_user.id,
    )
    db_session.add(c)
    await db_session.flush()
    return c


class TestInboundReplyNotify:
    @pytest.mark.asyncio
    async def test_reply_creates_inbound_notification_and_email(
        self, db_session: AsyncSession, test_user, gmail_connection, owned_contact
    ):
        """Inbound with in_reply_to set → InboundEmail + Notification + EmailQueue."""
        msg = _make_msg(
            from_="sender@client.com",
            to="owner@company.com",
            in_reply_to="<original@example.com>",
        )
        await _store_inbound(
            msg, gmail_connection, db_session, datetime.now(timezone.utc)
        )
        await db_session.flush()

        inbound_rows = (await db_session.execute(select(InboundEmail))).scalars().all()
        assert len(inbound_rows) == 1

        notif_rows = (await db_session.execute(select(Notification))).scalars().all()
        assert len(notif_rows) == 1
        assert notif_rows[0].type == "email_reply"
        assert notif_rows[0].user_id == test_user.id

        email_rows = (await db_session.execute(
            select(EmailQueue).where(EmailQueue.sent_by_id == test_user.id)
        )).scalars().all()
        assert len(email_rows) == 1
        assert email_rows[0].subject.startswith("Reply received —")

    @pytest.mark.asyncio
    async def test_cold_inbound_no_notification(
        self, db_session: AsyncSession, test_user, gmail_connection, owned_contact
    ):
        """Inbound without in_reply_to (cold) → InboundEmail created, no Notification."""
        msg = _make_msg(
            from_="sender@client.com",
            to="owner@company.com",
            in_reply_to=None,
        )
        await _store_inbound(
            msg, gmail_connection, db_session, datetime.now(timezone.utc)
        )
        await db_session.flush()

        inbound_rows = (await db_session.execute(select(InboundEmail))).scalars().all()
        assert len(inbound_rows) == 1

        notif_rows = (await db_session.execute(select(Notification))).scalars().all()
        assert len(notif_rows) == 0

        email_rows = (await db_session.execute(select(EmailQueue))).scalars().all()
        assert len(email_rows) == 0

    @pytest.mark.asyncio
    async def test_reply_no_owner_no_notification(
        self, db_session: AsyncSession, test_user, gmail_connection
    ):
        """Contact with no owner_id → no Notification, no EmailQueue."""
        unowned = Contact(
            email="unowned@client.com",
            first_name="Unowned",
            last_name="Contact",
            owner_id=None,
        )
        db_session.add(unowned)
        await db_session.flush()

        msg = _make_msg(
            from_="unowned@client.com",
            to="owner@company.com",
            in_reply_to="<original@example.com>",
            raw_id="gmailid002",
            message_id="<msg-002@example.com>",
        )
        await _store_inbound(
            msg, gmail_connection, db_session, datetime.now(timezone.utc)
        )
        await db_session.flush()

        inbound_rows = (await db_session.execute(select(InboundEmail))).scalars().all()
        assert len(inbound_rows) == 1

        notif_rows = (await db_session.execute(select(Notification))).scalars().all()
        assert len(notif_rows) == 0

        email_rows = (await db_session.execute(select(EmailQueue))).scalars().all()
        assert len(email_rows) == 0

    @pytest.mark.asyncio
    async def test_reply_email_pref_off_notification_yes_email_no(
        self, db_session: AsyncSession, test_user, gmail_connection, owned_contact
    ):
        """event_matrix email=False → Notification row created, EmailQueue NOT created."""
        prefs = UserNotificationPrefs(
            user_id=test_user.id,
            in_app_enabled=True,
            email_enabled=True,
            email_digest="instant",
            event_matrix={"email_reply_received": {"email": False}},
        )
        db_session.add(prefs)
        await db_session.flush()

        msg = _make_msg(
            from_="sender@client.com",
            to="owner@company.com",
            in_reply_to="<original@example.com>",
        )
        await _store_inbound(
            msg, gmail_connection, db_session, datetime.now(timezone.utc)
        )
        await db_session.flush()

        notif_rows = (await db_session.execute(select(Notification))).scalars().all()
        assert len(notif_rows) == 1
        assert notif_rows[0].type == "email_reply"

        email_rows = (await db_session.execute(
            select(EmailQueue).where(EmailQueue.sent_by_id == test_user.id)
        )).scalars().all()
        assert len(email_rows) == 0
