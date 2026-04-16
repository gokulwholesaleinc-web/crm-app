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
) -> dict:
    return {
        "id": msg_id,
        "threadId": thread_id,
        "payload": {
            "mimeType": "multipart/alternative",
            "headers": [
                {"name": "Subject", "value": subject},
                {"name": "From", "value": from_},
                {"name": "To", "value": to},
                {"name": "Message-ID", "value": f"<{msg_id}@gmail.example.com>"},
                {"name": "Date", "value": date},
            ],
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
