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
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from src.database import Base
from src.auth.models import User
from src.contacts.models import Contact
from src.email.models import EmailQueue, InboundEmail
from src.integrations.gmail.models import GmailBackfillState, GmailConnection, GmailSyncState
from src.integrations.gmail.sync import GmailSyncWorker


# ---------------------------------------------------------------------------
# In-memory DB fixtures
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
        # Backfill drops messages without a contact link, so seed a contact
        # whose email matches the inbound sender.
        db.add(Contact(email="sender@client.com", first_name="Sender", last_name="Client", owner_id=test_user.id))
        await db.commit()
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
        assert rows[0].entity_type == "contacts"

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

        # Seed contacts so the contact-link gate doesn't drop these.
        db.add(Contact(email="a@client.com", first_name="A", last_name="Client", owner_id=test_user.id))
        db.add(Contact(email="b@client.com", first_name="B", last_name="Client", owner_id=test_user.id))
        await db.commit()

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
        db.add(Contact(email="c@client.com", first_name="C", last_name="Client", owner_id=test_user.id))
        await db.commit()
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


# ---------------------------------------------------------------------------
# Tests: send-as alias handling
# ---------------------------------------------------------------------------

class TestBackfillSendAsAliases:
    """Cover the giancarlo@/accounting@ case: connection.email is the primary
    Gmail address, but the user sends as a verified alias. Outbound from the
    alias must classify as sent and the alias must self-exclude from contact
    matching."""

    @pytest.mark.asyncio
    async def test_outbound_from_alias_classified_as_sent(
        self, connection, db, test_user
    ):
        """Message From=alias must land in EmailQueue (sent), not InboundEmail."""
        connection.aliases = [connection.email.lower(), "alias@example.com"]
        db.add(connection)
        # Recipient must be a known contact for backfill's contact-link gate.
        db.add(Contact(
            email="customer@biz.com",
            first_name="C", last_name="ust",
            owner_id=test_user.id,
        ))
        await db.commit()

        msg = _gmail_message(
            "alias_send_1", "t_alias_send",
            from_="alias@example.com",
            to="customer@biz.com",
            subject="From the alias",
        )
        routes = {
            "users/me/messages": {"messages": [{"id": "alias_send_1"}]},
            "users/me/messages/alias_send_1": msg,
        }
        http = _make_http_client(routes)

        with _patch_gmail_client(http):
            await GmailSyncWorker.backfill(connection, db, days=10)

        sent_rows = (await db.execute(select(EmailQueue))).scalars().all()
        assert len(sent_rows) == 1
        assert sent_rows[0].status == "sent"
        # Persist the actual sending address (the alias) — relink + UI
        # depend on this being the address Gmail's Sent folder shows.
        assert sent_rows[0].from_email == "alias@example.com"

        ib_rows = (await db.execute(select(InboundEmail))).scalars().all()
        assert ib_rows == [], "Outbound-from-alias must not become an inbound row"

    @pytest.mark.asyncio
    async def test_alias_excluded_from_contact_match(
        self, connection, db, test_user
    ):
        """An alias appearing in CC must not link the message to a contact whose
        email happens to equal the alias — the matcher self-excludes the full
        alias set, not just the primary."""
        connection.aliases = [connection.email.lower(), "alias@example.com"]
        # Self-card mirroring Giancarlo's bug: a contact exists at the alias
        # address (created automatically or by mistake). Without self-exclude
        # the matcher would link inbound mail to this contact.
        self_card = Contact(
            email="alias@example.com",
            first_name="Self", last_name="Card",
            owner_id=test_user.id,
        )
        real_contact = Contact(
            email="third@example.com",
            first_name="Real", last_name="Sender",
            owner_id=test_user.id,
        )
        db.add_all([self_card, real_contact])
        await db.commit()
        await db.refresh(self_card)
        await db.refresh(real_contact)

        # Inbound: real third-party sends to the primary, CC's the user's alias.
        msg = {
            "id": "self_exclude_1",
            "threadId": "t_self_exclude",
            "payload": {
                "mimeType": "multipart/alternative",
                "headers": [
                    {"name": "Subject", "value": "to alias"},
                    {"name": "From", "value": "third@example.com"},
                    {"name": "To", "value": connection.email},
                    {"name": "Cc", "value": "alias@example.com"},
                    {"name": "Message-ID", "value": "<self_exclude_1@gmail.example.com>"},
                    {"name": "Date", "value": "Mon, 14 Apr 2025 10:00:00 +0000"},
                ],
                "parts": [
                    {"mimeType": "text/plain", "body": {"data": _b64("body")}},
                ],
            },
        }
        routes = {
            "users/me/messages": {"messages": [{"id": "self_exclude_1"}]},
            "users/me/messages/self_exclude_1": msg,
        }
        http = _make_http_client(routes)

        with _patch_gmail_client(http):
            await GmailSyncWorker.backfill(connection, db, days=10)

        ib = (await db.execute(select(InboundEmail))).scalar_one()
        assert ib.entity_type == "contacts"
        assert ib.entity_id == real_contact.id
        assert ib.entity_id != self_card.id, (
            "Alias must self-exclude — the matcher must not link to the alias contact"
        )


# ---------------------------------------------------------------------------
# Tests: list_send_as
# ---------------------------------------------------------------------------

class TestGmailClientListSendAs:
    @pytest.mark.asyncio
    async def test_returns_only_accepted_aliases(self, connection, db):
        """Only verificationStatus=='accepted', or unset on isPrimary=True, is returned."""
        from src.integrations.gmail.client import GmailClient

        routes = {
            "users/me/settings/sendAs": {
                "sendAs": [
                    {"sendAsEmail": "primary@example.com", "isPrimary": True},
                    {"sendAsEmail": "alias@example.com", "verificationStatus": "accepted"},
                    {"sendAsEmail": "pending@example.com", "verificationStatus": "pending"},
                    # Non-primary entry with missing verificationStatus must NOT
                    # be accepted — that path is reserved for the primary.
                    {"sendAsEmail": "missing-status@example.com"},
                ]
            },
        }
        http = _make_http_client(routes)

        async with GmailClient(connection, db, http=http) as client:
            aliases = await client.list_send_as()

        assert "primary@example.com" in aliases
        assert "alias@example.com" in aliases
        assert "pending@example.com" not in aliases
        assert "missing-status@example.com" not in aliases

    @pytest.mark.asyncio
    async def test_returns_empty_on_403(self, connection, db):
        """Non-Workspace accounts can 403 the endpoint — degrade gracefully."""
        from src.integrations.gmail.client import GmailClient

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(403, json={"error": "forbidden"})

        http = httpx.AsyncClient(transport=httpx.MockTransport(handler))

        async with GmailClient(connection, db, http=http) as client:
            aliases = await client.list_send_as()

        assert aliases == []

    @pytest.mark.asyncio
    async def test_5xx_raises(self, connection, db):
        """Transient 5xx must propagate — returning [] would let refresh_aliases
        clobber a previously-good list."""
        from src.integrations.gmail.client import GmailClient

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, json={"error": "service unavailable"})

        http = httpx.AsyncClient(transport=httpx.MockTransport(handler))

        async with GmailClient(connection, db, http=http) as client:
            with pytest.raises(httpx.HTTPStatusError):
                await client.list_send_as()


# ---------------------------------------------------------------------------
# Tests: refresh_aliases clobber prevention
# ---------------------------------------------------------------------------

class TestRefreshAliasesClobberPrevention:
    @pytest.mark.asyncio
    async def test_empty_response_does_not_overwrite_populated_row(
        self, connection, db
    ):
        """If the API succeeds but returns [] while the row already has aliases,
        keep last-known-good. A 403 hitting an account that was working
        yesterday must not regress its alias set."""
        from src.integrations.gmail.service import GmailConnectionService

        connection.aliases = [connection.email.lower(), "alias@example.com"]
        db.add(connection)
        await db.commit()

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(403, json={"error": "forbidden"})

        http = httpx.AsyncClient(transport=httpx.MockTransport(handler))

        with _patch_gmail_client(http):
            service = GmailConnectionService(db)
            result = await service.refresh_aliases(connection)

        await db.refresh(connection)
        assert "alias@example.com" in connection.aliases
        assert "alias@example.com" in result

    @pytest.mark.asyncio
    async def test_empty_response_on_empty_row_persists_empty(
        self, connection, db
    ):
        """First-time pull returning [] (e.g. account genuinely has no
        aliases AND none were stored before) writes []. Otherwise the row
        would never get populated."""
        from src.integrations.gmail.service import GmailConnectionService

        # Default fixture leaves aliases unpopulated.
        assert not connection.aliases

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(403, json={"error": "forbidden"})

        http = httpx.AsyncClient(transport=httpx.MockTransport(handler))

        with _patch_gmail_client(http):
            service = GmailConnectionService(db)
            result = await service.refresh_aliases(connection)

        assert result == []
        await db.refresh(connection)
        assert list(connection.aliases or []) == []
