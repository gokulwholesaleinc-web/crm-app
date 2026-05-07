"""
Unit tests for GmailClient using httpx.MockTransport.

Covers: send_message b64 encoding, list_history_since pagination,
get_message header extraction, _refresh_if_needed on expired token.
"""

import base64
import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.integrations.gmail.client import (
    GmailAuthError,
    GmailClient,
    _first_address,
    _hydrate_inline_attachments,
    _parse_address_list,
)
from src.integrations.gmail.models import GmailConnection

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
    conn.token_expiry = token_expiry or datetime.now(UTC) + timedelta(hours=1)
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

    @pytest.mark.asyncio
    async def test_inline_cid_image_substituted_into_body_html(self):
        """An <img src="cid:..."> in body_html with a matching inline image
        part should be rewritten to a data: URI so the browser can render
        it. This is the regression for Giancarlo's "image shows as link
        instead of rendering" complaint.
        """
        import base64
        png_bytes = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
            b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
            b"\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa6"
            b"\xa3\x10\x84\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        png_b64url = base64.urlsafe_b64encode(png_bytes).decode().rstrip("=")
        html = b'<p>logo: <img src="cid:logo123" alt="logo"></p>'
        payload = {
            "id": "m1",
            "threadId": "t1",
            "payload": {
                "mimeType": "multipart/related",
                "headers": [
                    {"name": "Subject", "value": "Inline image"},
                    {"name": "From", "value": "s@example.com"},
                    {"name": "To", "value": "me@example.com"},
                    {"name": "Date", "value": "Mon, 14 Apr 2025 10:00:00 +0000"},
                ],
                "parts": [
                    {
                        "mimeType": "text/html",
                        "body": {"data": base64.urlsafe_b64encode(html).decode()},
                    },
                    {
                        "mimeType": "image/png",
                        "filename": "logo.png",
                        "headers": [
                            {"name": "Content-ID", "value": "<logo123>"},
                            {"name": "Content-Disposition", "value": "inline"},
                        ],
                        "body": {"data": png_b64url, "size": len(png_bytes)},
                    },
                ],
            },
        }
        client, _ = _make_client(_make_conn(), payload)
        msg = await client.get_message("m1")

        assert msg["body_html"] is not None
        assert "cid:logo123" not in msg["body_html"]
        assert "data:image/png;base64," in msg["body_html"]
        # Attachment metadata is preserved + flagged inline.
        items = (msg.get("attachments") or [])
        assert any(a["filename"] == "logo.png" and a["is_inline"] for a in items)

    @pytest.mark.asyncio
    async def test_oversized_inline_image_left_as_cid(self):
        """Don't embed images bigger than the inline cap; keep the cid:
        reference so the body row stays small. Reader sees a broken
        image rather than a 50MB body row.
        """
        import base64
        # Forge a part whose declared body size exceeds the cap. Decoded
        # bytes irrelevant — the cap check uses size first.
        big = b"\x00" * 5  # actual bytes don't matter for the size gate
        html = b'<img src="cid:huge">'
        payload = {
            "id": "m1",
            "threadId": "t1",
            "payload": {
                "mimeType": "multipart/related",
                "headers": [
                    {"name": "Subject", "value": "Big image"},
                    {"name": "From", "value": "s@example.com"},
                    {"name": "To", "value": "me@example.com"},
                    {"name": "Date", "value": "Mon, 14 Apr 2025 10:00:00 +0000"},
                ],
                "parts": [
                    {
                        "mimeType": "text/html",
                        "body": {"data": base64.urlsafe_b64encode(html).decode()},
                    },
                    {
                        "mimeType": "image/jpeg",
                        "filename": "huge.jpg",
                        "headers": [{"name": "Content-ID", "value": "<huge>"}],
                        "body": {
                            "data": base64.urlsafe_b64encode(big).decode(),
                            "size": 9_999_999,
                        },
                    },
                ],
            },
        }
        client, _ = _make_client(_make_conn(), payload)
        msg = await client.get_message("m1")
        assert "cid:huge" in (msg["body_html"] or "")
        assert "data:image/jpeg" not in (msg["body_html"] or "")

    @pytest.mark.asyncio
    async def test_inline_cid_image_substituted_when_src_is_unquoted(self):
        """Outlook-on-Windows + some Apple Mail variants emit
        ``<img src=cid:logo>`` (no quotes). The first regex pass only
        handled quoted refs; this verifies the unquoted branch fires
        too. Without it, Giancarlo's mail clients with Outlook-bouncers
        in the chain would still show broken images.
        """
        import base64
        png_bytes = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
            b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
            b"\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa6"
            b"\xa3\x10\x84\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        png_b64url = base64.urlsafe_b64encode(png_bytes).decode().rstrip("=")
        html = b"<p>logo: <img src=cid:logo123 alt=logo></p>"
        payload = {
            "id": "m1",
            "threadId": "t1",
            "payload": {
                "mimeType": "multipart/related",
                "headers": [
                    {"name": "Subject", "value": "Outlook unquoted"},
                    {"name": "From", "value": "s@example.com"},
                    {"name": "To", "value": "me@example.com"},
                    {"name": "Date", "value": "Mon, 14 Apr 2025 10:00:00 +0000"},
                ],
                "parts": [
                    {
                        "mimeType": "text/html",
                        "body": {"data": base64.urlsafe_b64encode(html).decode()},
                    },
                    {
                        "mimeType": "image/png",
                        "filename": "logo.png",
                        "headers": [
                            {"name": "Content-ID", "value": "<logo123>"},
                            {"name": "Content-Disposition", "value": "inline"},
                        ],
                        "body": {"data": png_b64url, "size": len(png_bytes)},
                    },
                ],
            },
        }
        client, _ = _make_client(_make_conn(), payload)
        msg = await client.get_message("m1")

        assert "cid:logo123" not in msg["body_html"]
        assert "data:image/png;base64," in msg["body_html"]

    @pytest.mark.asyncio
    async def test_inline_cid_duplicate_last_wins(self):
        """RFC 2392 forbids duplicate Content-IDs but real senders do it.
        When two image parts share the same cid, the last walked one
        wins. Behavior-preserving regression guard so a future
        well-intentioned "first wins" rewrite doesn't silently change
        which logo renders.
        """
        import base64
        red_png = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
            b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
            b"\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa6"
            b"\xa3\x10\x84\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        # Different but valid PNG bytes for the second part.
        blue_png = red_png + b"\x00"  # any byte difference is enough; the test
        # only cares that the resulting data: URI is the LATER one.
        html = b'<img src="cid:dup">'
        payload = {
            "id": "m1",
            "threadId": "t1",
            "payload": {
                "mimeType": "multipart/related",
                "headers": [
                    {"name": "Subject", "value": "dup cid"},
                    {"name": "From", "value": "s@example.com"},
                    {"name": "To", "value": "me@example.com"},
                    {"name": "Date", "value": "Mon, 14 Apr 2025 10:00:00 +0000"},
                ],
                "parts": [
                    {
                        "mimeType": "text/html",
                        "body": {"data": base64.urlsafe_b64encode(html).decode()},
                    },
                    {
                        "mimeType": "image/png",
                        "filename": "first.png",
                        "headers": [{"name": "Content-ID", "value": "<dup>"}],
                        "body": {
                            "data": base64.urlsafe_b64encode(red_png).decode().rstrip("="),
                            "size": len(red_png),
                        },
                    },
                    {
                        "mimeType": "image/png",
                        "filename": "second.png",
                        "headers": [{"name": "Content-ID", "value": "<dup>"}],
                        "body": {
                            "data": base64.urlsafe_b64encode(blue_png).decode().rstrip("="),
                            "size": len(blue_png),
                        },
                    },
                ],
            },
        }
        client, _ = _make_client(_make_conn(), payload)
        msg = await client.get_message("m1")

        assert "data:image/png;base64," in msg["body_html"]
        # Last-wins: the substituted URI corresponds to blue_png.
        expected_b64 = base64.b64encode(blue_png).decode("ascii")
        assert expected_b64 in msg["body_html"]

    def test_inline_cid_decode_failure_logs_with_message_id(
        self, caplog, monkeypatch,
    ):
        """When base64 decoding fails for a single inline image, the
        warning must include the gmail_msg_id so an operator chasing
        "logo broken on email X" can grep prod logs by message id
        instead of guessing across high-cardinality cid collisions.

        ``base64.urlsafe_b64decode`` is tolerant by default (silently
        skips non-alphabet chars), so triggering the ``except`` branch
        with raw inputs is unreliable. Patch the decoder to raise so
        the regression specifically targets the log-correlation
        contract.
        """
        import logging

        import src.integrations.gmail.client as client_mod
        from src.integrations.gmail.client import _inline_cid_images

        def _raise(_data: bytes) -> bytes:
            raise ValueError("forced decode failure")

        monkeypatch.setattr(client_mod.base64, "urlsafe_b64decode", _raise)

        attachments = [
            {
                "cid": "logo",
                "mime_type": "image/png",
                "data": "anything",
                "size": 50,
                "filename": "logo.png",
                "attachment_id": None,
            },
        ]
        html = '<p><img src="cid:logo" alt="x"></p>'

        with caplog.at_level(
            logging.WARNING, logger="src.integrations.gmail.client",
        ):
            out = _inline_cid_images(
                html, attachments, gmail_msg_id="msg-correlation-id-7",
            )

        # Substitution didn't happen — the broken cid: stayed.
        assert "cid:logo" in out
        assert "data:image/png;base64," not in out

        # And the warning carries gmail_msg_id for correlation.
        decode_warnings = [
            r for r in caplog.records
            if "[inline_cid] base64 decode failed" in r.getMessage()
        ]
        assert decode_warnings, "expected base64-decode warning to fire"
        assert "gmail_msg_id=msg-correlation-id-7" in decode_warnings[0].getMessage()
        assert "cid=logo" in decode_warnings[0].getMessage()

    @pytest.mark.asyncio
    async def test_attachments_metadata_collected_for_non_inline(self):
        """Non-inline attachments (no Content-ID) appear in
        msg['attachments'] with attachment_id so a future download UI
        can fetch them. Body_html is untouched since there's nothing
        to substitute.
        """
        import base64
        payload = {
            "id": "m1",
            "threadId": "t1",
            "payload": {
                "mimeType": "multipart/mixed",
                "headers": [
                    {"name": "Subject", "value": "PDF attached"},
                    {"name": "From", "value": "s@example.com"},
                    {"name": "To", "value": "me@example.com"},
                    {"name": "Date", "value": "Mon, 14 Apr 2025 10:00:00 +0000"},
                ],
                "parts": [
                    {
                        "mimeType": "text/plain",
                        "body": {"data": base64.urlsafe_b64encode(b"see attached").decode()},
                    },
                    {
                        "mimeType": "application/pdf",
                        "filename": "contract.pdf",
                        "body": {"attachmentId": "ANGjdJxxxx", "size": 100_000},
                    },
                ],
            },
        }
        client, _ = _make_client(_make_conn(), payload)
        msg = await client.get_message("m1")
        items = msg.get("attachments") or []
        assert any(
            a["filename"] == "contract.pdf"
            and a["attachment_id"] == "ANGjdJxxxx"
            and a["is_inline"] is False
            for a in items
        )


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
            token_expiry=datetime.now(UTC) - timedelta(seconds=10),
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

        conn = _make_conn(token_expiry=datetime.now(UTC) + timedelta(hours=1))
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
            token_expiry=datetime.now(UTC) - timedelta(seconds=10)
        )
        db = AsyncMock(spec=AsyncSession)
        http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        client = GmailClient(conn, db, http=http)

        with pytest.raises(GmailAuthError):
            await client.get_profile()

    @pytest.mark.asyncio
    async def test_raises_auth_error_when_refresh_returns_400_invalid_grant(self, monkeypatch):
        """Regression: Google returns 400 + invalid_grant when a refresh
        token is revoked or expired (Testing-mode apps after ~7 days).
        Older code only caught 401 and the connection got stuck in a
        "Connected but stale" state. The refresh handler must convert
        any 400/401 from the token endpoint into GmailAuthError."""
        import src.integrations.gmail.client as client_mod
        monkeypatch.setattr(client_mod, "_get_client_id", lambda: "cid")
        monkeypatch.setattr(client_mod, "_get_client_secret", lambda: "csecret")

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, json={"error": "invalid_grant"})

        conn = _make_conn(
            token_expiry=datetime.now(UTC) - timedelta(seconds=10)
        )
        db = AsyncMock(spec=AsyncSession)
        http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        client = GmailClient(conn, db, http=http)

        with pytest.raises(GmailAuthError):
            await client.get_profile()


# ---------------------------------------------------------------------------
# Address-list parsing
# ---------------------------------------------------------------------------

class TestParseAddressList:
    def test_empty_returns_empty_list(self):
        assert _parse_address_list("") == []
        assert _parse_address_list("   ") == []

    def test_single_bare_email(self):
        assert _parse_address_list("a@b.com") == ["a@b.com"]

    def test_single_with_display_name(self):
        assert _parse_address_list("Alice <a@b.com>") == ["a@b.com"]

    def test_multiple_comma_separated(self):
        result = _parse_address_list("a@b.com, c@d.com, e@f.com")
        assert result == ["a@b.com", "c@d.com", "e@f.com"]

    def test_quoted_display_name_with_comma(self):
        """A quoted display name containing a comma must NOT be split."""
        result = _parse_address_list('"Doe, Jane" <j@x.com>, bob@y.com')
        assert result == ["j@x.com", "bob@y.com"]

    def test_drops_malformed_entries(self):
        """Entries without an @ should be silently dropped."""
        result = _parse_address_list("garbage, valid@x.com, also-bad")
        assert result == ["valid@x.com"]

    def test_first_address_extracts_first(self):
        """_first_address must keep returning the leading email even after refactor."""
        assert _first_address("a@b.com, c@d.com") == "a@b.com"
        assert _first_address('"Doe, Jane" <j@x.com>, bob@y.com') == "j@x.com"
        assert _first_address("") == ""


# ---------------------------------------------------------------------------
# get_attachment
# ---------------------------------------------------------------------------

class TestGetAttachment:
    @pytest.mark.asyncio
    async def test_get_attachment_returns_data(self):
        """get_attachment should return the base64url data string on 200."""
        fake_data = "SGVsbG8gV29ybGQ"  # "Hello World" in base64url

        def handler(request: httpx.Request) -> httpx.Response:
            assert "/attachments/att-abc" in str(request.url)
            return httpx.Response(200, json={"size": 11, "data": fake_data})

        conn = _make_conn()
        db = AsyncMock(spec=AsyncSession)
        http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        client = GmailClient(conn, db, http=http)

        result = await client.get_attachment("msg-1", "att-abc")

        assert result == fake_data

    @pytest.mark.asyncio
    async def test_get_attachment_returns_none_on_404(self):
        """get_attachment should return None when Gmail returns 404 (attachment GC'd)."""
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, json={"error": {"code": 404, "message": "Not Found"}})

        conn = _make_conn()
        db = AsyncMock(spec=AsyncSession)
        http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        client = GmailClient(conn, db, http=http)

        result = await client.get_attachment("msg-1", "att-gone")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_attachment_raises_auth_error_on_401(self):
        """get_attachment should raise GmailAuthError on 401 response."""
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"error": "invalid_credentials"})

        conn = _make_conn()
        db = AsyncMock(spec=AsyncSession)
        http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        client = GmailClient(conn, db, http=http)

        with pytest.raises(GmailAuthError):
            await client.get_attachment("msg-1", "att-xyz")


# ---------------------------------------------------------------------------
# _hydrate_inline_attachments
# ---------------------------------------------------------------------------

class TestHydrateInlineAttachments:
    @pytest.mark.asyncio
    async def test_hydrate_skips_parts_with_data(self):
        """Parts that already have data should be returned unchanged."""
        existing_data = "already-here-b64"
        attachments = [
            {
                "mime_type": "image/png",
                "filename": "logo.png",
                "cid": "logo",
                "size": 100,
                "data": existing_data,
                "attachment_id": "att-123",
            }
        ]

        conn = _make_conn()
        db = AsyncMock(spec=AsyncSession)
        # No HTTP responses needed — get_attachment should never be called.
        http = httpx.AsyncClient(transport=httpx.MockTransport(
            lambda req: httpx.Response(500, json={"error": "should not be called"})
        ))
        client = GmailClient(conn, db, http=http)

        result = await _hydrate_inline_attachments(client, "msg-1", attachments)

        assert len(result) == 1
        assert result[0]["data"] == existing_data

    @pytest.mark.asyncio
    async def test_hydrate_only_fetches_images(self):
        """Non-image parts with attachment_id must not trigger a fetch; only image/* does."""
        fetched_ids: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            # Record which attachment_id was requested
            parts = str(request.url).split("/attachments/")
            if len(parts) > 1:
                fetched_ids.append(parts[1])
            return httpx.Response(200, json={"data": "img-data-b64"})

        attachments = [
            {
                "mime_type": "image/png",
                "filename": "logo.png",
                "cid": "logo",
                "size": 100,
                "data": None,
                "attachment_id": "att-img",
            },
            {
                "mime_type": "application/pdf",
                "filename": "contract.pdf",
                "cid": None,
                "size": 50_000,
                "data": None,
                "attachment_id": "att-pdf",
            },
        ]

        conn = _make_conn()
        db = AsyncMock(spec=AsyncSession)
        http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        client = GmailClient(conn, db, http=http)

        result = await _hydrate_inline_attachments(client, "msg-1", attachments)

        # Only the image part triggered a fetch.
        assert fetched_ids == ["att-img"]
        # Image part now has data; PDF part is unchanged (no data).
        img_part = next(a for a in result if a["mime_type"] == "image/png")
        pdf_part = next(a for a in result if a["mime_type"] == "application/pdf")
        assert img_part["data"] == "img-data-b64"
        assert pdf_part["data"] is None

    @pytest.mark.asyncio
    async def test_hydrate_skips_image_without_cid(self):
        """An image part with attachment_id but no Content-ID is a regular
        downloadable attachment, NOT an inline cid: ref. Fetching it
        burns Gmail quota for nothing (the data wouldn't be substituted
        anywhere). Must skip without a request.
        """
        fetch_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal fetch_count
            fetch_count += 1
            return httpx.Response(200, json={"data": "x"})

        attachments = [
            {
                "mime_type": "image/jpeg",
                "filename": "photo.jpg",
                "cid": None,  # regular attachment — not inline
                "size": 5000,
                "data": None,
                "attachment_id": "att-jpg",
            },
        ]
        conn = _make_conn()
        db = AsyncMock(spec=AsyncSession)
        http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        client = GmailClient(conn, db, http=http)

        result = await _hydrate_inline_attachments(client, "msg-1", attachments)
        assert fetch_count == 0
        assert result[0]["data"] is None

    @pytest.mark.asyncio
    async def test_hydrate_drops_oversize_actual_bytes(self, caplog):
        """Gmail's declared body.size is advisory. If a fetch returns
        actual bytes that exceed the 2.5MB cap, the part is dropped
        and a WARN log fires with declared vs. actual bytes — without
        the re-check, _inline_cid_images silently drops the substitution
        downstream and the operator sees a "broken logo" report with
        no log trail.
        """
        import base64
        import logging

        # 3MB of bytes — over the 2.5MB cap.
        big_bytes = b"\xff" * (3 * 1024 * 1024)
        big_b64url = base64.urlsafe_b64encode(big_bytes).decode().rstrip("=")

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"data": big_b64url})

        attachments = [
            {
                "mime_type": "image/png",
                "filename": "huge.png",
                "cid": "huge",
                "size": 100,  # advisory — way under the cap
                "data": None,
                "attachment_id": "att-huge",
            },
        ]
        conn = _make_conn()
        db = AsyncMock(spec=AsyncSession)
        http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        client = GmailClient(conn, db, http=http)

        with caplog.at_level(
            logging.WARNING, logger="src.integrations.gmail.client",
        ):
            result = await _hydrate_inline_attachments(
                client, "msg-oversize", attachments,
            )

        assert result[0]["data"] is None  # not hydrated
        oversize_logs = [
            r for r in caplog.records
            if "[hydrate_inline] oversize" in r.getMessage()
        ]
        assert oversize_logs, "expected oversize warn"
        msg = oversize_logs[0].getMessage()
        assert "gmail_msg_id=msg-oversize" in msg
        assert "attachment_id=att-huge" in msg
        assert "cid=huge" in msg

    @pytest.mark.asyncio
    async def test_hydrate_propagates_auth_error(self):
        """A 401 mid-hydration should propagate so the caller can mark
        the connection revoked. Swallowing it as a generic warning
        would log five identical lines while the real auth state
        silently rots.
        """
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"error": "invalid_token"})

        attachments = [
            {
                "mime_type": "image/png",
                "cid": "logo",
                "size": 100,
                "data": None,
                "attachment_id": "att-1",
                "filename": "logo.png",
            },
        ]
        conn = _make_conn()
        db = AsyncMock(spec=AsyncSession)
        http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        client = GmailClient(conn, db, http=http)

        with pytest.raises(GmailAuthError):
            await _hydrate_inline_attachments(client, "msg-401", attachments)


# ---------------------------------------------------------------------------
# get_message — post-hydration CID substitution
# ---------------------------------------------------------------------------

class TestGetMessageHydration:
    @pytest.mark.asyncio
    async def test_get_message_substitutes_cid_after_hydration(self):
        """End-to-end: a message with cid: ref + image part that only has
        attachment_id (no inline data) should trigger get_attachment, and
        the returned data should be substituted into body_html as a data: URI.
        """
        import base64

        png_bytes = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
            b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
            b"\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa6"
            b"\xa3\x10\x84\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        png_b64url = base64.urlsafe_b64encode(png_bytes).decode().rstrip("=")
        html = b'<p>logo: <img src="cid:fetched-logo" alt="logo"></p>'

        # First response: the full message (image part has only attachmentId, no data)
        gmail_message = {
            "id": "msg-hydrate-1",
            "threadId": "t1",
            "payload": {
                "mimeType": "multipart/related",
                "headers": [
                    {"name": "Subject", "value": "Attachment hydration test"},
                    {"name": "From", "value": "s@example.com"},
                    {"name": "To", "value": "me@example.com"},
                    {"name": "Date", "value": "Mon, 14 Apr 2025 10:00:00 +0000"},
                ],
                "parts": [
                    {
                        "mimeType": "text/html",
                        "body": {"data": base64.urlsafe_b64encode(html).decode()},
                    },
                    {
                        "mimeType": "image/png",
                        "filename": "logo.png",
                        "headers": [
                            {"name": "Content-ID", "value": "<fetched-logo>"},
                            {"name": "Content-Disposition", "value": "inline"},
                        ],
                        # No inline data — only attachmentId (simulates large image)
                        "body": {"attachmentId": "att-fetch-me", "size": 500},
                    },
                ],
            },
        }

        call_count = [0]

        def handler(request: httpx.Request) -> httpx.Response:
            call_count[0] += 1
            url = str(request.url)
            if "/attachments/att-fetch-me" in url:
                return httpx.Response(200, json={"data": png_b64url, "size": len(png_bytes)})
            # messages.get call
            return httpx.Response(200, json=gmail_message)

        conn = _make_conn()
        db = AsyncMock(spec=AsyncSession)
        http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        client = GmailClient(conn, db, http=http)

        msg = await client.get_message("msg-hydrate-1")

        assert msg["body_html"] is not None
        assert "cid:fetched-logo" not in msg["body_html"]
        assert "data:image/png;base64," in msg["body_html"]
