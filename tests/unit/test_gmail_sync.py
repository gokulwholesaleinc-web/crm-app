"""
Unit tests for GmailSyncWorker.

Uses SQLite in-memory DB (same pattern as existing tests) and
httpx.MockTransport for Gmail API calls.

Covers:
- first-run seeds historyId without writing email rows
- inbound message creates InboundEmail, dedupes on second call
- outbound (from phone) creates EmailQueue with sent_via='gmail'
- same Message-ID seen twice produces no duplicate rows
"""

import base64
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import os
import sys

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy import select

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from src.database import Base
from src.auth.models import User
from src.contacts.models import Contact
from src.email.models import EmailQueue, InboundEmail
from src.integrations.gmail.models import GmailConnection, GmailSyncState
from src.integrations.gmail.sync import GmailSyncWorker


# ---------------------------------------------------------------------------
# In-memory DB fixtures (scoped per test)
# ---------------------------------------------------------------------------

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine(
        TEST_DB_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()


@pytest_asyncio.fixture
async def db(engine) -> AsyncSession:
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def test_user(db: AsyncSession) -> User:
    from src.auth.security import get_password_hash
    user = User(
        email="sync_user@example.com",
        hashed_password=get_password_hash("pw"),
        full_name="Sync User",
        is_active=True,
        is_superuser=False,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def connection(db: AsyncSession, test_user: User) -> GmailConnection:
    conn = GmailConnection(
        user_id=test_user.id,
        email="sync_user@example.com",
        access_token="tok",
        refresh_token="rtok",
        token_expiry=datetime.now(timezone.utc) + timedelta(hours=1),
        scopes="https://mail.google.com/",
    )
    db.add(conn)
    await db.commit()
    await db.refresh(conn)
    return conn


# ---------------------------------------------------------------------------
# Gmail API mock helpers
# ---------------------------------------------------------------------------

def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode()


def _gmail_message(
    msg_id: str,
    thread_id: str,
    from_: str,
    to: str,
    subject: str = "Test Subject",
    body: str = "Hello",
    date: str = "Mon, 14 Apr 2025 10:00:00 +0000",
    cc: str | None = None,
    bcc: str | None = None,
) -> dict:
    headers = [
        {"name": "Subject", "value": subject},
        {"name": "From", "value": from_},
        {"name": "To", "value": to},
        {"name": "Message-ID", "value": f"<{msg_id}@gmail.example.com>"},
        {"name": "Date", "value": date},
    ]
    if cc:
        headers.append({"name": "Cc", "value": cc})
    if bcc:
        headers.append({"name": "Bcc", "value": bcc})
    return {
        "id": msg_id,
        "threadId": thread_id,
        "payload": {
            "mimeType": "multipart/alternative",
            "headers": headers,
            "parts": [
                {"mimeType": "text/plain", "body": {"data": _b64(body)}},
            ],
        },
    }


def _make_http_client(routes: dict[str, dict]) -> httpx.AsyncClient:
    """routes maps URL-substring → response dict."""

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        for key, resp in routes.items():
            if key in url:
                return httpx.Response(200, json=resp)
        return httpx.Response(404, json={"error": "not found"})

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSyncFirstRun:
    @pytest.mark.asyncio
    async def test_first_run_seeds_history_id_and_returns(self, connection, db):
        """First sync with no cursor should seed historyId and write no email rows."""
        routes = {
            "users/me/profile": {"emailAddress": connection.email, "historyId": "500"},
        }
        http = _make_http_client(routes)

        with patch("src.integrations.gmail.client.httpx.AsyncClient", return_value=http):
            from src.integrations.gmail.client import GmailClient as _GC
            orig_init = _GC.__init__

            def patched_init(self, conn, db_, http=None):
                orig_init(self, conn, db_, http=http)

            with patch.object(_GC, "__init__", patched_init):
                await GmailSyncWorker.sync_account(connection, db)

        state = (await db.execute(
            select(GmailSyncState).where(GmailSyncState.user_id == connection.user_id)
        )).scalar_one_or_none()

        assert state is not None
        assert state.last_history_id == "500"

        eq_count = (await db.execute(select(EmailQueue))).scalars().all()
        ib_count = (await db.execute(select(InboundEmail))).scalars().all()
        assert len(eq_count) == 0
        assert len(ib_count) == 0


class TestSyncInbound:
    @pytest.mark.asyncio
    async def test_inbound_message_creates_inbound_email(self, connection, db, test_user):
        """Second sync with inbound message should create an InboundEmail row."""
        state = GmailSyncState(
            user_id=connection.user_id,
            last_history_id="100",
            failure_count=0,
        )
        db.add(state)
        await db.commit()

        msg = _gmail_message(
            msg_id="abc123",
            thread_id="t1",
            from_="customer@client.com",
            to=connection.email,
            body="I'd like to schedule a call",
        )
        history = {
            "history": [
                {"id": "101", "messagesAdded": [{"message": {"id": "abc123"}}]}
            ]
        }

        routes = {
            "users/me/history": history,
            f"users/me/messages/abc123": msg,
        }
        http = _make_http_client(routes)

        with patch("src.integrations.gmail.client.httpx.AsyncClient", return_value=http):
            from src.integrations.gmail.client import GmailClient as _GC
            orig_init = _GC.__init__

            def patched_init(self, conn, db_, http=None):
                orig_init(self, conn, db_, http=http)

            with patch.object(_GC, "__init__", patched_init):
                await GmailSyncWorker.sync_account(connection, db)

        rows = (await db.execute(select(InboundEmail))).scalars().all()
        assert len(rows) == 1
        assert rows[0].from_email == "customer@client.com"
        assert rows[0].subject == "Test Subject"
        assert rows[0].message_id == "<abc123@gmail.example.com>"

    @pytest.mark.asyncio
    async def test_inbound_dedupes_on_second_run(self, connection, db, test_user):
        """Same message seen on two syncs should not create duplicate InboundEmail rows."""
        state = GmailSyncState(
            user_id=connection.user_id,
            last_history_id="100",
            failure_count=0,
        )
        db.add(state)
        await db.commit()

        msg = _gmail_message(
            msg_id="dup123",
            thread_id="t1",
            from_="other@client.com",
            to=connection.email,
        )
        history = {
            "history": [
                {"id": "101", "messagesAdded": [{"message": {"id": "dup123"}}]}
            ]
        }

        routes = {
            "users/me/history": history,
            "users/me/messages/dup123": msg,
        }
        http = _make_http_client(routes)

        with patch("src.integrations.gmail.client.httpx.AsyncClient", return_value=http):
            from src.integrations.gmail.client import GmailClient as _GC
            orig_init = _GC.__init__

            def patched_init(self, conn, db_, http=None):
                orig_init(self, conn, db_, http=http)

            with patch.object(_GC, "__init__", patched_init):
                await GmailSyncWorker.sync_account(connection, db)
                # Reset cursor so the same history appears again
                state_row = (await db.execute(
                    select(GmailSyncState).where(GmailSyncState.user_id == connection.user_id)
                )).scalar_one()
                state_row.last_history_id = "100"
                db.add(state_row)
                await db.commit()

                await GmailSyncWorker.sync_account(connection, db)

        rows = (await db.execute(select(InboundEmail))).scalars().all()
        assert len(rows) == 1, "Should not create duplicate inbound row"


class TestSyncOutbound:
    @pytest.mark.asyncio
    async def test_outbound_from_phone_creates_email_queue_row(self, connection, db, test_user):
        """Message sent FROM the connection email should create EmailQueue with sent_via='gmail'."""
        state = GmailSyncState(
            user_id=connection.user_id,
            last_history_id="200",
            failure_count=0,
        )
        db.add(state)
        await db.commit()

        msg = _gmail_message(
            msg_id="sent456",
            thread_id="t2",
            from_=connection.email,
            to="prospect@corp.com",
            subject="Following up",
            body="Just checking in",
        )
        history = {
            "history": [
                {"id": "201", "messagesAdded": [{"message": {"id": "sent456"}}]}
            ]
        }

        routes = {
            "users/me/history": history,
            "users/me/messages/sent456": msg,
        }
        http = _make_http_client(routes)

        with patch("src.integrations.gmail.client.httpx.AsyncClient", return_value=http):
            from src.integrations.gmail.client import GmailClient as _GC
            orig_init = _GC.__init__

            def patched_init(self, conn, db_, http=None):
                orig_init(self, conn, db_, http=http)

            with patch.object(_GC, "__init__", patched_init):
                await GmailSyncWorker.sync_account(connection, db)

        rows = (await db.execute(select(EmailQueue))).scalars().all()
        assert len(rows) == 1
        eq = rows[0]
        assert eq.sent_via == "gmail"
        assert eq.status == "sent"
        assert eq.from_email == connection.email
        assert eq.to_email == "prospect@corp.com"
        assert eq.subject == "Following up"
        assert eq.message_id == "<sent456@gmail.example.com>"
        assert eq.sent_by_id == connection.user_id

        ib_rows = (await db.execute(select(InboundEmail))).scalars().all()
        assert len(ib_rows) == 0


class TestSyncDedupe:
    @pytest.mark.asyncio
    async def test_same_message_id_in_email_queue_skips_inbound(self, connection, db, test_user):
        """If Message-ID already in email_queue, sync should not create InboundEmail."""
        state = GmailSyncState(
            user_id=connection.user_id,
            last_history_id="300",
            failure_count=0,
        )
        db.add(state)

        # Pre-populate EmailQueue with the same message_id
        existing = EmailQueue(
            to_email="me@example.com",
            from_email="other@example.com",
            subject="Already tracked",
            body="body",
            status="sent",
            sent_via="gmail",
            message_id="<exist789@gmail.example.com>",
            sent_by_id=test_user.id,
        )
        db.add(existing)
        await db.commit()

        msg = _gmail_message(
            msg_id="exist789",
            thread_id="t3",
            from_="other@example.com",
            to=connection.email,
        )
        history = {
            "history": [
                {"id": "301", "messagesAdded": [{"message": {"id": "exist789"}}]}
            ]
        }

        routes = {
            "users/me/history": history,
            "users/me/messages/exist789": msg,
        }
        http = _make_http_client(routes)

        with patch("src.integrations.gmail.client.httpx.AsyncClient", return_value=http):
            from src.integrations.gmail.client import GmailClient as _GC
            orig_init = _GC.__init__

            def patched_init(self, conn, db_, http=None):
                orig_init(self, conn, db_, http=http)

            with patch.object(_GC, "__init__", patched_init):
                await GmailSyncWorker.sync_account(connection, db)

        ib_rows = (await db.execute(select(InboundEmail))).scalars().all()
        assert len(ib_rows) == 0, "Duplicate Message-ID should be skipped"

    @pytest.mark.asyncio
    async def test_contact_matched_by_from_email(self, connection, db, test_user):
        """Inbound from a known contact email should link entity_type/entity_id."""
        contact = Contact(
            email="known@client.com",
            first_name="Known",
            last_name="Client",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db.add(contact)
        await db.commit()
        await db.refresh(contact)

        state = GmailSyncState(
            user_id=connection.user_id,
            last_history_id="400",
            failure_count=0,
        )
        db.add(state)
        await db.commit()

        msg = _gmail_message(
            msg_id="linked001",
            thread_id="t4",
            from_="known@client.com",
            to=connection.email,
            subject="Question about pricing",
        )
        history = {
            "history": [
                {"id": "401", "messagesAdded": [{"message": {"id": "linked001"}}]}
            ]
        }

        routes = {
            "users/me/history": history,
            "users/me/messages/linked001": msg,
        }
        http = _make_http_client(routes)

        with patch("src.integrations.gmail.client.httpx.AsyncClient", return_value=http):
            from src.integrations.gmail.client import GmailClient as _GC
            orig_init = _GC.__init__

            def patched_init(self, conn, db_, http=None):
                orig_init(self, conn, db_, http=http)

            with patch.object(_GC, "__init__", patched_init):
                await GmailSyncWorker.sync_account(connection, db)

        rows = (await db.execute(select(InboundEmail))).scalars().all()
        assert len(rows) == 1
        assert rows[0].entity_type == "contacts"
        assert rows[0].entity_id == contact.id


class TestSyncThreadFallback:
    """Replies sent/received outside CRM keep the Gmail threadId but can use
    addresses that don't match any Contact. The sync worker should fall back
    to the thread's existing entity link so the reply lands on the contact."""

    @pytest.mark.asyncio
    async def test_outbound_reply_links_via_thread_when_to_unknown(
        self, connection, db, test_user
    ):
        contact = Contact(
            email="known@client.com",
            first_name="Known",
            last_name="Client",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db.add(contact)
        await db.commit()
        await db.refresh(contact)

        prior = EmailQueue(
            to_email="known@client.com",
            from_email=connection.email,
            subject="First touch",
            body="hi",
            status="sent",
            sent_via="gmail",
            message_id="<orig@gmail.example.com>",
            thread_id="thread-xyz",
            sent_by_id=test_user.id,
            entity_type="contacts",
            entity_id=contact.id,
        )
        db.add(prior)
        state = GmailSyncState(
            user_id=connection.user_id, last_history_id="500", failure_count=0,
        )
        db.add(state)
        await db.commit()

        msg = _gmail_message(
            msg_id="reply999",
            thread_id="thread-xyz",
            from_=connection.email,
            to="someone-else@random.com",
            subject="Re: First touch",
        )
        history = {
            "history": [{"id": "501", "messagesAdded": [{"message": {"id": "reply999"}}]}]
        }
        routes = {
            "users/me/history": history,
            "users/me/messages/reply999": msg,
        }
        http = _make_http_client(routes)

        with patch("src.integrations.gmail.client.httpx.AsyncClient", return_value=http):
            from src.integrations.gmail.client import GmailClient as _GC
            orig_init = _GC.__init__

            def patched_init(self, conn, db_, http=None):
                orig_init(self, conn, db_, http=http)

            with patch.object(_GC, "__init__", patched_init):
                await GmailSyncWorker.sync_account(connection, db)

        reply = (await db.execute(
            select(EmailQueue).where(EmailQueue.message_id == "<reply999@gmail.example.com>")
        )).scalar_one()
        assert reply.entity_type == "contacts"
        assert reply.entity_id == contact.id

    @pytest.mark.asyncio
    async def test_inbound_reply_links_via_thread_when_from_unknown(
        self, connection, db, test_user
    ):
        contact = Contact(
            email="known@client.com",
            first_name="Known",
            last_name="Client",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db.add(contact)
        await db.commit()
        await db.refresh(contact)

        prior_inbound = InboundEmail(
            resend_email_id="gmail:first-inbound",
            from_email="known@client.com",
            to_email=connection.email,
            subject="First inbound",
            message_id="<first@gmail.example.com>",
            thread_id="thread-abc",
            received_at=datetime.now(timezone.utc),
            entity_type="contacts",
            entity_id=contact.id,
        )
        db.add(prior_inbound)
        state = GmailSyncState(
            user_id=connection.user_id, last_history_id="600", failure_count=0,
        )
        db.add(state)
        await db.commit()

        msg = _gmail_message(
            msg_id="colleague1",
            thread_id="thread-abc",
            from_="colleague@client.com",
            to=connection.email,
            subject="Re: First inbound",
        )
        history = {
            "history": [{"id": "601", "messagesAdded": [{"message": {"id": "colleague1"}}]}]
        }
        routes = {
            "users/me/history": history,
            "users/me/messages/colleague1": msg,
        }
        http = _make_http_client(routes)

        with patch("src.integrations.gmail.client.httpx.AsyncClient", return_value=http):
            from src.integrations.gmail.client import GmailClient as _GC
            orig_init = _GC.__init__

            def patched_init(self, conn, db_, http=None):
                orig_init(self, conn, db_, http=http)

            with patch.object(_GC, "__init__", patched_init):
                await GmailSyncWorker.sync_account(connection, db)

        reply = (await db.execute(
            select(InboundEmail).where(InboundEmail.message_id == "<colleague1@gmail.example.com>")
        )).scalar_one()
        assert reply.entity_type == "contacts"
        assert reply.entity_id == contact.id

    @pytest.mark.asyncio
    async def test_thread_fallback_is_tenant_scoped(self, connection, db, test_user):
        """A prior thread row owned by a different user must NOT leak its
        contact link to this user's sync."""
        from src.auth.security import get_password_hash
        other_user = User(
            email="other_user@example.com",
            hashed_password=get_password_hash("pw"),
            full_name="Other",
            is_active=True,
            is_superuser=False,
        )
        db.add(other_user)
        await db.commit()
        await db.refresh(other_user)

        other_contact = Contact(
            email="stranger@client.com",
            first_name="Stranger",
            last_name="Co",
            owner_id=other_user.id,
            created_by_id=other_user.id,
        )
        db.add(other_contact)
        await db.commit()
        await db.refresh(other_contact)

        db.add(EmailQueue(
            to_email="stranger@client.com",
            from_email="other_user@example.com",
            subject="Other user's thread",
            body="hi",
            status="sent",
            sent_via="gmail",
            message_id="<other@gmail.example.com>",
            thread_id="shared-thread-id",
            sent_by_id=other_user.id,
            entity_type="contacts",
            entity_id=other_contact.id,
        ))
        db.add(GmailSyncState(
            user_id=connection.user_id, last_history_id="700", failure_count=0,
        ))
        await db.commit()

        msg = _gmail_message(
            msg_id="mine001",
            thread_id="shared-thread-id",
            from_=connection.email,
            to="new-lead@corp.com",
            subject="Unrelated",
        )
        history = {
            "history": [{"id": "701", "messagesAdded": [{"message": {"id": "mine001"}}]}]
        }
        routes = {
            "users/me/history": history,
            "users/me/messages/mine001": msg,
        }
        http = _make_http_client(routes)

        with patch("src.integrations.gmail.client.httpx.AsyncClient", return_value=http):
            from src.integrations.gmail.client import GmailClient as _GC
            orig_init = _GC.__init__

            def patched_init(self, conn, db_, http=None):
                orig_init(self, conn, db_, http=http)

            with patch.object(_GC, "__init__", patched_init):
                await GmailSyncWorker.sync_account(connection, db)

        reply = (await db.execute(
            select(EmailQueue).where(EmailQueue.message_id == "<mine001@gmail.example.com>")
        )).scalar_one()
        assert reply.entity_type is None
        assert reply.entity_id is None

    @pytest.mark.asyncio
    async def test_unknown_thread_with_unmatched_recipient_persists_unlinked(
        self, connection, db, test_user
    ):
        """No prior thread + no matching contact → row still persists, unlinked."""
        state = GmailSyncState(
            user_id=connection.user_id, last_history_id="800", failure_count=0,
        )
        db.add(state)
        await db.commit()

        msg = _gmail_message(
            msg_id="orphan1",
            thread_id="fresh-thread",
            from_=connection.email,
            to="nobody@nowhere.com",
            subject="Cold outreach",
        )
        history = {
            "history": [{"id": "801", "messagesAdded": [{"message": {"id": "orphan1"}}]}]
        }
        routes = {
            "users/me/history": history,
            "users/me/messages/orphan1": msg,
        }
        http = _make_http_client(routes)

        with patch("src.integrations.gmail.client.httpx.AsyncClient", return_value=http):
            from src.integrations.gmail.client import GmailClient as _GC
            orig_init = _GC.__init__

            def patched_init(self, conn, db_, http=None):
                orig_init(self, conn, db_, http=http)

            with patch.object(_GC, "__init__", patched_init):
                await GmailSyncWorker.sync_account(connection, db)

        row = (await db.execute(
            select(EmailQueue).where(EmailQueue.message_id == "<orphan1@gmail.example.com>")
        )).scalar_one()
        assert row.entity_type is None
        assert row.entity_id is None


class TestSyncMultiRecipient:
    """Coverage for the multi-recipient parsing fix.

    Pre-fix, `_store_inbound`/`_store_sent` only matched against the
    single from_email or To[0] address; CRM contacts in CC or in
    position 2+ of the To: header were silently dropped to entity_id=NULL.
    """

    @pytest.mark.asyncio
    async def test_inbound_links_when_contact_in_cc_position(
        self, connection, db, test_user
    ):
        contact = Contact(
            email="cc-only@client.com",
            first_name="CC",
            last_name="Only",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db.add(contact)
        state = GmailSyncState(
            user_id=connection.user_id, last_history_id="900", failure_count=0,
        )
        db.add(state)
        await db.commit()
        await db.refresh(contact)

        msg = _gmail_message(
            msg_id="cc-msg",
            thread_id="t-cc",
            from_="someone@external.com",
            to=connection.email,
            cc="someone-else@elsewhere.com, CC Only <cc-only@client.com>",
            subject="Loop you in",
        )
        history = {
            "history": [{"id": "901", "messagesAdded": [{"message": {"id": "cc-msg"}}]}]
        }
        routes = {
            "users/me/history": history,
            "users/me/messages/cc-msg": msg,
        }
        http = _make_http_client(routes)

        with patch("src.integrations.gmail.client.httpx.AsyncClient", return_value=http):
            from src.integrations.gmail.client import GmailClient as _GC
            orig_init = _GC.__init__

            def patched_init(self, conn, db_, http=None):
                orig_init(self, conn, db_, http=http)

            with patch.object(_GC, "__init__", patched_init):
                await GmailSyncWorker.sync_account(connection, db)

        row = (await db.execute(
            select(InboundEmail).where(InboundEmail.message_id == "<cc-msg@gmail.example.com>")
        )).scalar_one()
        assert row.entity_type == "contacts"
        assert row.entity_id == contact.id
        assert "cc-only@client.com" in (row.cc or "")

    @pytest.mark.asyncio
    async def test_sent_links_when_contact_is_third_to_recipient(
        self, connection, db, test_user
    ):
        contact = Contact(
            email="third@client.com",
            first_name="Third",
            last_name="Recipient",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db.add(contact)
        state = GmailSyncState(
            user_id=connection.user_id, last_history_id="950", failure_count=0,
        )
        db.add(state)
        await db.commit()
        await db.refresh(contact)

        msg = _gmail_message(
            msg_id="multi-to",
            thread_id="t-multi",
            from_=connection.email,
            to="first@noisy.com, second@noisy.com, Third <third@client.com>",
            subject="Group blast",
        )
        history = {
            "history": [{"id": "951", "messagesAdded": [{"message": {"id": "multi-to"}}]}]
        }
        routes = {
            "users/me/history": history,
            "users/me/messages/multi-to": msg,
        }
        http = _make_http_client(routes)

        with patch("src.integrations.gmail.client.httpx.AsyncClient", return_value=http):
            from src.integrations.gmail.client import GmailClient as _GC
            orig_init = _GC.__init__

            def patched_init(self, conn, db_, http=None):
                orig_init(self, conn, db_, http=http)

            with patch.object(_GC, "__init__", patched_init):
                await GmailSyncWorker.sync_account(connection, db)

        row = (await db.execute(
            select(EmailQueue).where(EmailQueue.message_id == "<multi-to@gmail.example.com>")
        )).scalar_one()
        assert row.entity_type == "contacts"
        assert row.entity_id == contact.id

    @pytest.mark.asyncio
    async def test_inbound_links_via_bcc_when_contact_only_in_to(
        self, connection, db, test_user
    ):
        """Contact in TO of an inbound where receiver is BCC'd still matches."""
        contact = Contact(
            email="vip@client.com",
            first_name="VIP",
            last_name="Client",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db.add(contact)
        state = GmailSyncState(
            user_id=connection.user_id, last_history_id="970", failure_count=0,
        )
        db.add(state)
        await db.commit()
        await db.refresh(contact)

        msg = _gmail_message(
            msg_id="bcc-msg",
            thread_id="t-bcc",
            from_="vendor@thirdparty.com",
            to="vip@client.com",
            bcc=connection.email,
            subject="Quote",
        )
        history = {
            "history": [{"id": "971", "messagesAdded": [{"message": {"id": "bcc-msg"}}]}]
        }
        routes = {
            "users/me/history": history,
            "users/me/messages/bcc-msg": msg,
        }
        http = _make_http_client(routes)

        with patch("src.integrations.gmail.client.httpx.AsyncClient", return_value=http):
            from src.integrations.gmail.client import GmailClient as _GC
            orig_init = _GC.__init__

            def patched_init(self, conn, db_, http=None):
                orig_init(self, conn, db_, http=http)

            with patch.object(_GC, "__init__", patched_init):
                await GmailSyncWorker.sync_account(connection, db)

        row = (await db.execute(
            select(InboundEmail).where(InboundEmail.message_id == "<bcc-msg@gmail.example.com>")
        )).scalar_one()
        assert row.entity_type == "contacts"
        assert row.entity_id == contact.id

    @pytest.mark.asyncio
    async def test_quoted_display_name_with_comma_does_not_split(
        self, connection, db, test_user
    ):
        """``"Doe, Jane" <j@x.com>`` must not be parsed as two addresses."""
        contact = Contact(
            email="j@x.com",
            first_name="Jane",
            last_name="Doe",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db.add(contact)
        state = GmailSyncState(
            user_id=connection.user_id, last_history_id="990", failure_count=0,
        )
        db.add(state)
        await db.commit()
        await db.refresh(contact)

        msg = _gmail_message(
            msg_id="quoted-name",
            thread_id="t-quoted",
            from_=connection.email,
            to='"Doe, Jane" <j@x.com>',
            subject="Hi Jane",
        )
        history = {
            "history": [{"id": "991", "messagesAdded": [{"message": {"id": "quoted-name"}}]}]
        }
        routes = {
            "users/me/history": history,
            "users/me/messages/quoted-name": msg,
        }
        http = _make_http_client(routes)

        with patch("src.integrations.gmail.client.httpx.AsyncClient", return_value=http):
            from src.integrations.gmail.client import GmailClient as _GC
            orig_init = _GC.__init__

            def patched_init(self, conn, db_, http=None):
                orig_init(self, conn, db_, http=http)

            with patch.object(_GC, "__init__", patched_init):
                await GmailSyncWorker.sync_account(connection, db)

        row = (await db.execute(
            select(EmailQueue).where(EmailQueue.message_id == "<quoted-name@gmail.example.com>")
        )).scalar_one()
        assert row.entity_type == "contacts"
        assert row.entity_id == contact.id
