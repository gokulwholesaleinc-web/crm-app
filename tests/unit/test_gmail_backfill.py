"""
Unit tests for GmailSyncWorker.backfill.

Uses SQLite in-memory DB + httpx.MockTransport at the GmailClient boundary
(same pattern as test_gmail_client.py / test_gmail_sync.py).

Covers:
- 1-page list_messages_since → single page, all messages processed
- Multi-page pagination follows nextPageToken
- Idempotency: re-run after a prior backfill doesn't duplicate rows
- Thread-stitching: backfilled message inherits entity link from prior forward-sync row
- 401/400 from refresh token converts to GmailAuthError + connection.revoked_at flips
"""

import base64
import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from src.database import Base
from src.auth.models import User
from src.contacts.models import Contact
from src.email.models import EmailQueue, InboundEmail
from src.integrations.gmail.models import GmailBackfillState, GmailConnection, GmailSyncState
from src.integrations.gmail.sync import GmailSyncWorker
from ._engine import is_postgres, make_test_engine


# ---------------------------------------------------------------------------
# DB fixtures (env-aware: Postgres in CI, SQLite locally)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def engine():
    eng = make_test_engine()
    async with eng.begin() as conn:
        if is_postgres():
            await conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
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
        email="backfill_user@example.com",
        hashed_password=get_password_hash("pw"),
        full_name="Backfill User",
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
        email="backfill_user@example.com",
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
# HTTP mock helpers
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
                {"name": "Date", "value": "Mon, 14 Apr 2025 10:00:00 +0000"},
            ],
            "parts": [
                {"mimeType": "text/plain", "body": {"data": _b64(body)}},
            ],
        },
    }


def _make_http_client(routes: dict[str, dict | tuple]) -> httpx.AsyncClient:
    """routes maps URL-substring → (response_dict, status) or just response_dict.

    Longer (more specific) keys take priority so /messages/abc123 wins over
    /messages even when both are present.
    """
    sorted_routes = sorted(routes.items(), key=lambda kv: -len(kv[0]))

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        for key, resp in sorted_routes:
            if key in url:
                if isinstance(resp, tuple):
                    body, status = resp
                    return httpx.Response(status, json=body)
                return httpx.Response(200, json=resp)
        return httpx.Response(404, json={"error": "not found"})

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _patch_gmail_client(http: httpx.AsyncClient):
    """Context manager that injects a pre-built httpx client into GmailClient."""
    from src.integrations.gmail.client import GmailClient as _GC

    orig_init = _GC.__init__

    def patched_init(self, conn, db_, http_arg=None):
        orig_init(self, conn, db_, http=http_arg or http)

    return patch.object(_GC, "__init__", patched_init)


# ---------------------------------------------------------------------------
# Tests: single page
# ---------------------------------------------------------------------------

class TestBackfillSinglePage:
    @pytest.mark.asyncio
    async def test_single_page_creates_inbound_emails(self, connection, db, test_user):
        """Backfill with one page of results should persist all messages."""
        msg = _gmail_message(
            "bf001", "t1", "sender@client.com", connection.email, body="Hi there"
        )
        routes = {
            "users/me/messages": {
                "messages": [{"id": "bf001"}],
            },
            "users/me/messages/bf001": msg,
        }
        http = _make_http_client(routes)

        with _patch_gmail_client(http):
            await GmailSyncWorker.backfill(connection, db, days=30)

        rows = (await db.execute(select(InboundEmail))).scalars().all()
        assert len(rows) == 1
        assert rows[0].from_email == "sender@client.com"

    @pytest.mark.asyncio
    async def test_backfill_state_set_complete(self, connection, db, test_user):
        """After a successful backfill, GmailBackfillState.status == 'complete'."""
        routes = {
            "users/me/messages": {"messages": []},
        }
        http = _make_http_client(routes)

        with _patch_gmail_client(http):
            await GmailSyncWorker.backfill(connection, db, days=1)

        state = (await db.execute(
            select(GmailBackfillState).where(GmailBackfillState.user_id == connection.user_id)
        )).scalar_one_or_none()

        assert state is not None
        assert state.status == "complete"
        assert state.finished_at is not None


# ---------------------------------------------------------------------------
# Tests: multi-page pagination
# ---------------------------------------------------------------------------

class TestBackfillPagination:
    @pytest.mark.asyncio
    async def test_multi_page_processes_all_messages(self, connection, db, test_user):
        """list_messages_since should follow nextPageToken until exhausted."""
        seen_params: list[dict] = []

        msg_a = _gmail_message("pa1", "ta", "a@client.com", connection.email)
        msg_b = _gmail_message("pb1", "tb", "b@client.com", connection.email)

        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            params = dict(request.url.params)

            if "users/me/messages/pa1" in url:
                return httpx.Response(200, json=msg_a)
            if "users/me/messages/pb1" in url:
                return httpx.Response(200, json=msg_b)
            if "users/me/messages" in url and "messages/" not in url:
                seen_params.append(params)
                if "pageToken" not in params:
                    return httpx.Response(200, json={
                        "messages": [{"id": "pa1"}],
                        "nextPageToken": "tok2",
                    })
                return httpx.Response(200, json={
                    "messages": [{"id": "pb1"}],
                })
            return httpx.Response(404, json={"error": "not found"})

        http = httpx.AsyncClient(transport=httpx.MockTransport(handler))

        with _patch_gmail_client(http):
            await GmailSyncWorker.backfill(connection, db, days=30)

        rows = (await db.execute(select(InboundEmail))).scalars().all()
        assert len(rows) == 2
        assert {r.from_email for r in rows} == {"a@client.com", "b@client.com"}
        # Second request had the page token
        assert seen_params[1].get("pageToken") == "tok2"


# ---------------------------------------------------------------------------
# Tests: idempotency
# ---------------------------------------------------------------------------

class TestBackfillIdempotency:
    @pytest.mark.asyncio
    async def test_rerun_does_not_duplicate_rows(self, connection, db, test_user):
        """Running backfill twice should not create duplicate email rows."""
        msg = _gmail_message("idem1", "t_idem", "c@client.com", connection.email)
        routes = {
            "users/me/messages": {"messages": [{"id": "idem1"}]},
            "users/me/messages/idem1": msg,
        }
        http = _make_http_client(routes)

        with _patch_gmail_client(http):
            await GmailSyncWorker.backfill(connection, db, days=10)

        # Reset state so second run is allowed
        state = (await db.execute(
            select(GmailBackfillState).where(GmailBackfillState.user_id == connection.user_id)
        )).scalar_one()
        state.status = "pending"
        db.add(state)
        await db.commit()

        http2 = _make_http_client(routes)
        with _patch_gmail_client(http2):
            await GmailSyncWorker.backfill(connection, db, days=10)

        rows = (await db.execute(select(InboundEmail))).scalars().all()
        assert len(rows) == 1, "Second backfill run must not duplicate rows"

    @pytest.mark.asyncio
    async def test_already_in_email_queue_skipped(self, connection, db, test_user):
        """Message-ID already in EmailQueue from forward sync must be skipped."""
        existing = EmailQueue(
            to_email=connection.email,
            from_email="known@client.com",
            subject="Prior send",
            body="body",
            status="sent",
            sent_via="gmail",
            message_id="<fwd001@gmail.example.com>",
            sent_by_id=test_user.id,
        )
        db.add(existing)
        await db.commit()

        msg = _gmail_message("fwd001", "t_fwd", "known@client.com", connection.email)
        routes = {
            "users/me/messages": {"messages": [{"id": "fwd001"}]},
            "users/me/messages/fwd001": msg,
        }
        http = _make_http_client(routes)

        with _patch_gmail_client(http):
            await GmailSyncWorker.backfill(connection, db, days=10)

        ib_rows = (await db.execute(select(InboundEmail))).scalars().all()
        assert len(ib_rows) == 0, "Row already in EmailQueue must not be duplicated to InboundEmail"


# ---------------------------------------------------------------------------
# Tests: thread-stitching
# ---------------------------------------------------------------------------

class TestBackfillThreadStitching:
    @pytest.mark.asyncio
    async def test_backfilled_message_inherits_entity_from_forward_sync_row(
        self, connection, db, test_user
    ):
        """Backfilled message on an existing thread should inherit entity_type/entity_id."""
        contact = Contact(
            email="prospect@corp.com",
            first_name="Prospect",
            last_name="Co",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db.add(contact)
        await db.commit()
        await db.refresh(contact)

        prior = EmailQueue(
            to_email="prospect@corp.com",
            from_email=connection.email,
            subject="First email",
            body="hi",
            status="sent",
            sent_via="gmail",
            message_id="<first@gmail.example.com>",
            thread_id="thread-stitch",
            sent_by_id=test_user.id,
            entity_type="contacts",
            entity_id=contact.id,
        )
        db.add(prior)
        await db.commit()

        # Backfill sees a reply from an unknown address on the same thread
        msg = _gmail_message(
            "reply_bf1", "thread-stitch", "colleague@corp.com", connection.email,
            subject="Re: First email"
        )
        routes = {
            "users/me/messages": {"messages": [{"id": "reply_bf1"}]},
            "users/me/messages/reply_bf1": msg,
        }
        http = _make_http_client(routes)

        with _patch_gmail_client(http):
            await GmailSyncWorker.backfill(connection, db, days=10)

        ib = (await db.execute(
            select(InboundEmail).where(
                InboundEmail.message_id == "<reply_bf1@gmail.example.com>"
            )
        )).scalar_one()
        assert ib.entity_type == "contacts"
        assert ib.entity_id == contact.id


# ---------------------------------------------------------------------------
# Tests: auth error handling
# ---------------------------------------------------------------------------

class TestBackfillAuthError:
    @pytest.mark.asyncio
    async def test_401_on_messages_list_marks_connection_revoked(
        self, connection, db, test_user, monkeypatch
    ):
        """A 401 from messages.list (via expired refresh token) must flip revoked_at."""
        import src.integrations.gmail.client as client_mod

        monkeypatch.setattr(client_mod, "_get_client_id", lambda: "cid")
        monkeypatch.setattr(client_mod, "_get_client_secret", lambda: "csecret")

        # Token is expired so client will try to refresh; refresh returns 401
        connection.token_expiry = datetime.now(timezone.utc) - timedelta(seconds=10)
        db.add(connection)
        await db.commit()

        def handler(request: httpx.Request) -> httpx.Response:
            # Every call returns 401 including the refresh attempt
            return httpx.Response(401, json={"error": "invalid_token"})

        http = httpx.AsyncClient(transport=httpx.MockTransport(handler))

        from src.integrations.gmail.client import GmailAuthError

        with _patch_gmail_client(http):
            with pytest.raises(GmailAuthError):
                await GmailSyncWorker.backfill(connection, db, days=10)

        await db.refresh(connection)
        assert connection.revoked_at is not None

        state = (await db.execute(
            select(GmailBackfillState).where(GmailBackfillState.user_id == connection.user_id)
        )).scalar_one_or_none()
        assert state is not None
        assert state.status == "failed"

    @pytest.mark.asyncio
    async def test_400_invalid_grant_marks_connection_revoked(
        self, connection, db, test_user, monkeypatch
    ):
        """A 400 invalid_grant from token refresh must also flip revoked_at."""
        import src.integrations.gmail.client as client_mod

        monkeypatch.setattr(client_mod, "_get_client_id", lambda: "cid")
        monkeypatch.setattr(client_mod, "_get_client_secret", lambda: "csecret")

        connection.token_expiry = datetime.now(timezone.utc) - timedelta(seconds=10)
        db.add(connection)
        await db.commit()

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, json={"error": "invalid_grant"})

        http = httpx.AsyncClient(transport=httpx.MockTransport(handler))

        from src.integrations.gmail.client import GmailAuthError

        with _patch_gmail_client(http):
            with pytest.raises(GmailAuthError):
                await GmailSyncWorker.backfill(connection, db, days=10)

        await db.refresh(connection)
        assert connection.revoked_at is not None
