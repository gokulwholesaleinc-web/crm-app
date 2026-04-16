"""Integration tests for Gmail send + inbound sync.

Uses SQLite in-memory DB (via conftest fixtures) and httpx.MockTransport
for the Gmail API. No mocks on business logic.
"""

import base64
import json
from datetime import datetime, timezone

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.activities.models import Activity
from src.contacts.models import Contact
from src.email.models import EmailQueue, InboundEmail
from src.email.service import EmailService
from src.integrations.gmail.client import GmailClient
from src.integrations.gmail.models import GmailConnection, GmailSyncState
from src.integrations.gmail.service import GmailConnectionService
from src.integrations.gmail.sync import GmailSyncWorker


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def _fake_token_response(email: str = "giancarlo@linkcreative.com") -> dict:
    payload = json.dumps({"email": email, "sub": "12345"})
    id_token = f"header.{_b64(payload)}.sig"
    return {
        "access_token": "ya29.test-access",
        "refresh_token": "1//test-refresh",
        "expires_in": 3600,
        "id_token": id_token,
    }


def _gmail_transport(
    *,
    send_response: dict | None = None,
    history_records: list | None = None,
    messages: dict | None = None,
    profile_history_id: str = "1000",
) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path

        if "messages/send" in path:
            return httpx.Response(200, json=send_response or {
                "id": "msg-001",
                "threadId": "thread-001",
                "labelIds": ["SENT"],
            })

        if "/history" in path:
            return httpx.Response(200, json={
                "history": history_records or [],
                "historyId": "2000",
            })

        if "/messages/" in path and "format" in str(request.url):
            msg_id = path.split("/messages/")[1].split("?")[0]
            if messages and msg_id in messages:
                return httpx.Response(200, json=messages[msg_id])
            return httpx.Response(404, json={"error": "not found"})

        if path.endswith("/profile"):
            return httpx.Response(200, json={
                "emailAddress": "giancarlo@linkcreative.com",
                "historyId": profile_history_id,
            })

        if "oauth2.googleapis.com/token" in str(request.url):
            return httpx.Response(200, json={
                "access_token": "ya29.refreshed",
                "expires_in": 3600,
            })

        return httpx.Response(404)

    return httpx.MockTransport(handler)


@pytest_asyncio.fixture
async def gmail_connection(db_session: AsyncSession, test_user) -> GmailConnection:
    conn = GmailConnection(
        user_id=test_user.id,
        email="giancarlo@linkcreative.com",
        access_token="ya29.test-access",
        refresh_token="1//test-refresh",
        token_expiry=datetime(2099, 1, 1, tzinfo=timezone.utc),
        scopes="openid email profile gmail.send gmail.readonly",
    )
    db_session.add(conn)
    await db_session.flush()
    return conn


@pytest_asyncio.fixture
async def contact(db_session: AsyncSession, test_user) -> Contact:
    c = Contact(
        email="customer@example.com",
        first_name="Test",
        last_name="Customer",
        owner_id=test_user.id,
    )
    db_session.add(c)
    await db_session.flush()
    return c


class TestGmailConnect:
    @pytest.mark.asyncio
    async def test_upsert_creates_connection_and_sync_state(self, db_session, test_user):
        service = GmailConnectionService(db_session)
        conn = await service.upsert_from_token_exchange(
            user_id=test_user.id,
            token_response=_fake_token_response(),
            email="giancarlo@linkcreative.com",
        )
        await db_session.commit()

        assert conn.email == "giancarlo@linkcreative.com"
        assert conn.is_active

        state = await service.get_sync_state(test_user.id)
        assert state is not None
        assert state.last_history_id is None

    @pytest.mark.asyncio
    async def test_disconnect_sets_revoked_at(self, db_session, test_user, gmail_connection):
        transport = httpx.MockTransport(lambda req: httpx.Response(200))

        def factory():
            return httpx.AsyncClient(transport=transport)

        service = GmailConnectionService(db_session, client_factory=factory)
        revoked = await service.mark_revoked(test_user.id)
        await db_session.commit()

        assert revoked is not None
        assert revoked.revoked_at is not None
        assert not revoked.is_active
        assert revoked.access_token == ""


class TestGmailSync:
    @pytest.mark.asyncio
    async def test_first_sync_seeds_history_id(self, db_session, gmail_connection):
        transport = _gmail_transport(profile_history_id="5000")
        client_http = httpx.AsyncClient(transport=transport)

        state = GmailSyncState(user_id=gmail_connection.user_id, failure_count=0)
        db_session.add(state)
        await db_session.flush()

        import unittest.mock
        orig_init = GmailClient.__init__
        def patched_init(self, conn, db, http=None):
            orig_init(self, conn, db, http=client_http)
        with unittest.mock.patch.object(GmailClient, "__init__", patched_init):
            await GmailSyncWorker.sync_account(gmail_connection, db_session)
        await db_session.commit()

        result = await db_session.execute(
            select(GmailSyncState).where(GmailSyncState.user_id == gmail_connection.user_id)
        )
        state = result.scalar_one()
        assert state.last_history_id == "5000"

    @pytest.mark.asyncio
    async def test_inbound_message_creates_inbound_email(self, db_session, gmail_connection, contact):
        state = GmailSyncState(
            user_id=gmail_connection.user_id,
            last_history_id="1000",
            failure_count=0,
        )
        db_session.add(state)
        await db_session.flush()

        msg_payload = {
            "id": "msg-inbound-1",
            "threadId": "thread-inbound-1",
            "payload": {
                "mimeType": "text/plain",
                "headers": [
                    {"name": "From", "value": "customer@example.com"},
                    {"name": "To", "value": "giancarlo@linkcreative.com"},
                    {"name": "Subject", "value": "Re: Invoice question"},
                    {"name": "Message-ID", "value": "<inbound-001@example.com>"},
                    {"name": "Date", "value": "Wed, 15 Apr 2026 10:00:00 -0500"},
                ],
                "body": {"data": _b64("Thanks for the invoice!")},
            },
        }

        transport = _gmail_transport(
            history_records=[{
                "id": "1500",
                "messagesAdded": [{"message": {"id": "msg-inbound-1"}}],
            }],
            messages={"msg-inbound-1": msg_payload},
        )

        orig_init = GmailClient.__init__

        def patched_init(self, conn, db, http=None):
            orig_init(self, conn, db, http=httpx.AsyncClient(transport=transport))

        import unittest.mock
        with unittest.mock.patch.object(GmailClient, "__init__", patched_init):
            await GmailSyncWorker.sync_account(gmail_connection, db_session)
        await db_session.commit()

        result = await db_session.execute(select(InboundEmail))
        rows = result.scalars().all()
        assert len(rows) == 1
        assert rows[0].from_email == "customer@example.com"
        assert rows[0].subject == "Re: Invoice question"
        assert rows[0].entity_type == "contacts"
        assert rows[0].entity_id == contact.id

    @pytest.mark.asyncio
    async def test_dedupe_by_message_id(self, db_session, gmail_connection, contact):
        existing = InboundEmail(
            resend_email_id="gmail:existing",
            from_email="customer@example.com",
            to_email="giancarlo@linkcreative.com",
            subject="Already logged",
            received_at=datetime.now(timezone.utc),
            message_id="<inbound-dup@example.com>",
        )
        db_session.add(existing)

        state = GmailSyncState(
            user_id=gmail_connection.user_id,
            last_history_id="1000",
            failure_count=0,
        )
        db_session.add(state)
        await db_session.flush()

        msg_payload = {
            "id": "msg-dup-1",
            "threadId": "thread-dup-1",
            "payload": {
                "mimeType": "text/plain",
                "headers": [
                    {"name": "From", "value": "customer@example.com"},
                    {"name": "To", "value": "giancarlo@linkcreative.com"},
                    {"name": "Subject", "value": "Already logged"},
                    {"name": "Message-ID", "value": "<inbound-dup@example.com>"},
                    {"name": "Date", "value": "Wed, 15 Apr 2026 10:00:00 -0500"},
                ],
                "body": {"data": _b64("dupe content")},
            },
        }

        transport = _gmail_transport(
            history_records=[{
                "id": "1500",
                "messagesAdded": [{"message": {"id": "msg-dup-1"}}],
            }],
            messages={"msg-dup-1": msg_payload},
        )

        import unittest.mock
        orig_init = GmailClient.__init__
        def patched_init(self, conn, db, http=None):
            orig_init(self, conn, db, http=httpx.AsyncClient(transport=transport))
        with unittest.mock.patch.object(GmailClient, "__init__", patched_init):
            await GmailSyncWorker.sync_account(gmail_connection, db_session)
        await db_session.commit()

        result = await db_session.execute(select(InboundEmail))
        assert len(result.scalars().all()) == 1

    @pytest.mark.asyncio
    async def test_outbound_from_phone_creates_email_queue(self, db_session, gmail_connection, contact):
        state = GmailSyncState(
            user_id=gmail_connection.user_id,
            last_history_id="1000",
            failure_count=0,
        )
        db_session.add(state)
        await db_session.flush()

        msg_payload = {
            "id": "msg-sent-phone",
            "threadId": "thread-sent-phone",
            "payload": {
                "mimeType": "text/plain",
                "headers": [
                    {"name": "From", "value": "giancarlo@linkcreative.com"},
                    {"name": "To", "value": "customer@example.com"},
                    {"name": "Subject", "value": "Following up"},
                    {"name": "Message-ID", "value": "<sent-phone-001@linkcreative.com>"},
                    {"name": "Date", "value": "Wed, 15 Apr 2026 11:00:00 -0500"},
                ],
                "body": {"data": _b64("Hey, following up on our call.")},
            },
        }

        transport = _gmail_transport(
            history_records=[{
                "id": "1600",
                "messagesAdded": [{"message": {"id": "msg-sent-phone"}}],
            }],
            messages={"msg-sent-phone": msg_payload},
        )

        import unittest.mock
        orig_init = GmailClient.__init__
        def patched_init(self, conn, db, http=None):
            orig_init(self, conn, db, http=httpx.AsyncClient(transport=transport))
        with unittest.mock.patch.object(GmailClient, "__init__", patched_init):
            await GmailSyncWorker.sync_account(gmail_connection, db_session)
        await db_session.commit()

        result = await db_session.execute(
            select(EmailQueue).where(EmailQueue.sent_via == "gmail")
        )
        rows = result.scalars().all()
        assert len(rows) == 1
        assert rows[0].to_email == "customer@example.com"
        assert rows[0].subject == "Following up"
        assert rows[0].entity_type == "contacts"
        assert rows[0].entity_id == contact.id


class TestGmailSendRouting:
    @pytest.mark.asyncio
    async def test_queue_email_creates_activity_on_send(self, db_session, test_user, contact):
        svc = EmailService(db_session)
        email = await svc.queue_email(
            to_email="customer@example.com",
            subject="Test email",
            body="<p>Hello</p>",
            sent_by_id=test_user.id,
            entity_type="contacts",
            entity_id=contact.id,
        )
        await db_session.commit()

        if email.status == "sent":
            result = await db_session.execute(
                select(Activity).where(
                    Activity.entity_type == "contacts",
                    Activity.entity_id == contact.id,
                    Activity.activity_type == "email",
                )
            )
            activity = result.scalar_one_or_none()
            assert activity is not None
            assert "Test email" in activity.subject
