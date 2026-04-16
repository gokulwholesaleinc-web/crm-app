"""
Unit tests for GmailClient using httpx.MockTransport.

Covers: send_message b64 encoding, list_history_since pagination,
get_message header extraction, _refresh_if_needed on expired token.
"""

import base64
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from src.integrations.gmail.client import GmailAuthError, GmailClient
from src.integrations.gmail.models import GmailConnection, GmailSyncState


# ---------------------------------------------------------------------------
# Fake GmailConnection builder
# ---------------------------------------------------------------------------

def _make_conn(
    user_id: int = 1,
    email: str = "user@example.com",
    access_token: str = "valid-token",
    refresh_token: str = "refresh-tok",
    token_expiry: datetime | None = None,
) -> GmailConnection:
    conn = GmailConnection()
    conn.id = 1
    conn.user_id = user_id
    conn.email = email
    conn.access_token = access_token
    conn.refresh_token = refresh_token
    conn.token_expiry = token_expiry or datetime.now(timezone.utc) + timedelta(hours=1)
    conn.scopes = "https://mail.google.com/"
    conn.revoked_at = None
    return conn


# ---------------------------------------------------------------------------
# MockTransport helpers
# ---------------------------------------------------------------------------

def _json_transport(*responses: dict) -> httpx.MockTransport:
    """Return a MockTransport that cycles through given JSON response dicts."""
    call_count = [-1]

    def handler(request: httpx.Request) -> httpx.Response:
        call_count[0] += 1
        idx = min(call_count[0], len(responses) - 1)
        body, status = responses[idx] if isinstance(responses[idx], tuple) else (responses[idx], 200)
        return httpx.Response(status, json=body)

    return httpx.MockTransport(handler)


def _make_client(conn: GmailConnection, *responses) -> tuple[GmailClient, AsyncMock]:
    db = AsyncMock(spec=AsyncSession)
    db.add = MagicMock()
    db.commit = AsyncMock()
    transport = _json_transport(*responses)
    http = httpx.AsyncClient(transport=transport)
    return GmailClient(conn, db, http=http), db


# ---------------------------------------------------------------------------
# send_message
# ---------------------------------------------------------------------------

class TestSendMessage:
    @pytest.mark.asyncio
    async def test_base64url_encodes_raw_bytes(self):
        """send_message should base64url-encode raw bytes in request body."""
        raw = b"From: a@b.com\r\nTo: c@d.com\r\n\r\nHello"
        expected_b64 = base64.urlsafe_b64encode(raw).decode("ascii")

        sent_body: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            sent_body.update(json.loads(request.content))
            return httpx.Response(200, json={"id": "msg1", "threadId": "t1", "labelIds": ["SENT"]})

        conn = _make_conn()
        db = AsyncMock(spec=AsyncSession)
        http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        client = GmailClient(conn, db, http=http)

        result = await client.send_message(raw)

        assert sent_body["raw"] == expected_b64
        assert "threadId" not in sent_body
        assert result["id"] == "msg1"

    @pytest.mark.asyncio
    async def test_thread_id_included_when_provided(self):
        """send_message should include threadId in body when given."""
        sent_body: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            sent_body.update(json.loads(request.content))
            return httpx.Response(200, json={"id": "msg2", "threadId": "thread-xyz"})

        conn = _make_conn()
        db = AsyncMock(spec=AsyncSession)
        http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        client = GmailClient(conn, db, http=http)

        await client.send_message(b"raw", thread_id="thread-xyz")

        assert sent_body.get("threadId") == "thread-xyz"

    @pytest.mark.asyncio
    async def test_raises_auth_error_on_401(self):
        """send_message should raise GmailAuthError on 401 response."""
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"error": "invalid_token"})

        conn = _make_conn()
        db = AsyncMock(spec=AsyncSession)
        http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        client = GmailClient(conn, db, http=http)

        with pytest.raises(GmailAuthError):
            await client.send_message(b"raw")


# ---------------------------------------------------------------------------
# list_history_since
# ---------------------------------------------------------------------------

class TestListHistorySince:
    @pytest.mark.asyncio
    async def test_single_page_no_next_token(self):
        """list_history_since should return records when no nextPageToken."""
        page1 = {
            "history": [{"id": "100", "messagesAdded": [{"message": {"id": "m1"}}]}],
        }
        client, _ = _make_client(_make_conn(), page1)
        result = await client.list_history_since("99")

        assert len(result) == 1
        assert result[0]["id"] == "100"

    @pytest.mark.asyncio
    async def test_paginates_via_page_token(self):
        """list_history_since should follow nextPageToken until exhausted."""
        seen_params: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            params = dict(request.url.params)
            seen_params.append(params)
            if "pageToken" not in params:
                return httpx.Response(200, json={
                    "history": [{"id": "10"}],
                    "nextPageToken": "tok2",
                })
            return httpx.Response(200, json={
                "history": [{"id": "20"}],
            })

        conn = _make_conn()
        db = AsyncMock(spec=AsyncSession)
        http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        client = GmailClient(conn, db, http=http)

        result = await client.list_history_since("9")

        assert len(result) == 2
        assert result[0]["id"] == "10"
        assert result[1]["id"] == "20"
        assert seen_params[1].get("pageToken") == "tok2"

    @pytest.mark.asyncio
    async def test_empty_history_returns_empty_list(self):
        """list_history_since should return empty list when no history."""
        client, _ = _make_client(_make_conn(), {"history": []})
        result = await client.list_history_since("5")
        assert result == []


# ---------------------------------------------------------------------------
# get_message
# ---------------------------------------------------------------------------

def _make_gmail_message(
    msg_id: str = "m1",
    thread_id: str = "t1",
    subject: str = "Hello",
    from_: str = "sender@example.com",
    to: str = "me@example.com",
    body_text: str = "plain text body",
) -> dict:
    import base64

    text_data = base64.urlsafe_b64encode(body_text.encode()).decode()
    return {
        "id": msg_id,
        "threadId": thread_id,
        "payload": {
            "mimeType": "multipart/alternative",
            "headers": [
                {"name": "Subject", "value": subject},
                {"name": "From", "value": from_},
                {"name": "To", "value": to},
                {"name": "Message-ID", "value": f"<{msg_id}@mail.example.com>"},
                {"name": "In-Reply-To", "value": "<prev@mail.example.com>"},
                {"name": "References", "value": "<prev@mail.example.com>"},
                {"name": "Date", "value": "Mon, 14 Apr 2025 10:00:00 +0000"},
            ],
            "parts": [
                {
                    "mimeType": "text/plain",
                    "body": {"data": text_data},
                },
                {
                    "mimeType": "text/html",
                    "body": {"data": base64.urlsafe_b64encode(b"<p>plain text body</p>").decode()},
                },
            ],
        },
    }


class TestGetMessage:
    @pytest.mark.asyncio
    async def test_extracts_rfc_headers(self):
        """get_message should extract subject, from, to, message_id, in_reply_to."""
        payload = _make_gmail_message(
            subject="Re: Contract",
            from_="Bob <bob@example.com>",
            to="alice@example.com",
        )
        client, _ = _make_client(_make_conn(), payload)
        msg = await client.get_message("m1")

        assert msg["subject"] == "Re: Contract"
        assert msg["from"] == "bob@example.com"
        assert msg["to"] == "alice@example.com"
        assert msg["message_id"] == "<m1@mail.example.com>"
        assert msg["in_reply_to"] == "<prev@mail.example.com>"

    @pytest.mark.asyncio
    async def test_extracts_body_text_and_html(self):
        """get_message should populate body_text and body_html from MIME parts."""
        payload = _make_gmail_message(body_text="Hello world")
        client, _ = _make_client(_make_conn(), payload)
        msg = await client.get_message("m1")

        assert msg["body_text"] == "Hello world"
        assert "<p>" in (msg["body_html"] or "")

    @pytest.mark.asyncio
    async def test_parses_date_to_datetime(self):
        """get_message date field should be a datetime."""
        payload = _make_gmail_message()
        client, _ = _make_client(_make_conn(), payload)
        msg = await client.get_message("m1")

        assert isinstance(msg["date"], datetime)

    @pytest.mark.asyncio
    async def test_thread_id_populated(self):
        """get_message thread_id should match the Gmail threadId."""
        payload = _make_gmail_message(thread_id="thread-99")
        client, _ = _make_client(_make_conn(), payload)
        msg = await client.get_message("m1")

        assert msg["thread_id"] == "thread-99"


# ---------------------------------------------------------------------------
# _refresh_if_needed
# ---------------------------------------------------------------------------

class TestRefreshIfNeeded:
    @pytest.mark.asyncio
    async def test_refreshes_when_token_expired(self, monkeypatch):
        """_refresh_if_needed should POST to token endpoint and update connection."""
        import src.integrations.gmail.client as client_mod
        monkeypatch.setattr(client_mod, "_get_client_id", lambda: "cid")
        monkeypatch.setattr(client_mod, "_get_client_secret", lambda: "csecret")

        refresh_calls: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            if "oauth2.googleapis.com" in str(request.url):
                refresh_calls.append(dict(request.url.params))
                return httpx.Response(200, json={
                    "access_token": "new-token",
                    "expires_in": 3600,
                })
            # Any other request (profile)
            return httpx.Response(200, json={"emailAddress": "u@e.com", "historyId": "5"})

        conn = _make_conn(
            access_token="old-token",
            token_expiry=datetime.now(timezone.utc) - timedelta(seconds=10),
        )
        db = AsyncMock(spec=AsyncSession)
        db.add = MagicMock()
        db.commit = AsyncMock()
        http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        client = GmailClient(conn, db, http=http)

        await client.get_profile()

        assert conn.access_token == "new-token"
        assert db.commit.called

    @pytest.mark.asyncio
    async def test_skips_refresh_when_token_valid(self, monkeypatch):
        """_refresh_if_needed should not POST when token is still valid."""
        refresh_posts = []

        def handler(request: httpx.Request) -> httpx.Response:
            if "oauth2.googleapis.com" in str(request.url):
                refresh_posts.append(request)
            return httpx.Response(200, json={"emailAddress": "u@e.com", "historyId": "5"})

        conn = _make_conn(token_expiry=datetime.now(timezone.utc) + timedelta(hours=1))
        db = AsyncMock(spec=AsyncSession)
        http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        client = GmailClient(conn, db, http=http)

        await client.get_profile()

        assert refresh_posts == []

    @pytest.mark.asyncio
    async def test_raises_auth_error_when_refresh_returns_401(self, monkeypatch):
        """_refresh_if_needed should raise GmailAuthError when refresh returns 401."""
        import src.integrations.gmail.client as client_mod
        monkeypatch.setattr(client_mod, "_get_client_id", lambda: "cid")
        monkeypatch.setattr(client_mod, "_get_client_secret", lambda: "csecret")

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"error": "invalid_client"})

        conn = _make_conn(
            token_expiry=datetime.now(timezone.utc) - timedelta(seconds=10)
        )
        db = AsyncMock(spec=AsyncSession)
        http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        client = GmailClient(conn, db, http=http)

        with pytest.raises(GmailAuthError):
            await client.get_profile()
