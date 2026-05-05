"""Low-level Gmail API client — no FastAPI dependencies, no routes."""

import base64
import logging
from datetime import UTC, datetime, timedelta
from email.utils import getaddresses, parsedate_to_datetime

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from src.integrations.gmail.models import GmailConnection

logger = logging.getLogger(__name__)

_GMAIL_BASE = "https://gmail.googleapis.com/gmail/v1"
_TOKEN_URL = "https://oauth2.googleapis.com/token"


class GmailAuthError(Exception):
    """Raised when the Gmail API returns 401 — caller should mark connection failed."""


class GmailClient:
    def __init__(
        self,
        connection: GmailConnection,
        db: AsyncSession,
        http: httpx.AsyncClient | None = None,
    ):
        self._conn = connection
        self._db = db
        self._http = http or httpx.AsyncClient()
        self._own_http = http is None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        if self._own_http:
            await self._http.aclose()

    async def _refresh_if_needed(self) -> None:
        now = datetime.now(UTC)
        expiry = self._conn.token_expiry
        if expiry is not None and expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=UTC)
        if expiry is not None and expiry > now:
            return
        if not self._conn.refresh_token:
            return

        resp = await self._http.post(
            _TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": self._conn.refresh_token,
                "client_id": _get_client_id(),
                "client_secret": _get_client_secret(),
            },
        )
        # Google returns 400 with body `{"error": "invalid_grant"}` when a
        # refresh token has been revoked or expired (Testing-mode apps lose
        # refresh tokens after 7 days). Older code only caught 401, so the
        # 400 fell through to raise_for_status() and the connection got
        # stuck in "Connected" state with a stale `last_error`. Treat both
        # as auth failures so sync_account marks the connection revoked
        # and the UI prompts for reconnect.
        if resp.status_code in (400, 401):
            try:
                err = resp.json().get("error", "")
            except ValueError:
                err = ""
            raise GmailAuthError(
                f"Refresh token rejected by Google ({resp.status_code} {err})"
            )
        resp.raise_for_status()
        data = resp.json()
        self._conn.access_token = data["access_token"]
        expires_in = data.get("expires_in", 3600)
        self._conn.token_expiry = now + timedelta(seconds=expires_in)
        self._db.add(self._conn)
        await self._db.commit()

    def _auth_headers(self) -> dict:
        return {"Authorization": f"Bearer {self._conn.access_token}"}

    async def _get(self, path: str, **params) -> dict:
        await self._refresh_if_needed()
        url = f"{_GMAIL_BASE}/{path}"
        resp = await self._http.get(url, headers=self._auth_headers(), params=params)
        if resp.status_code == 401:
            raise GmailAuthError(f"401 on GET {path}")
        resp.raise_for_status()
        return resp.json()

    async def _post(self, path: str, body: dict) -> dict:
        await self._refresh_if_needed()
        url = f"{_GMAIL_BASE}/{path}"
        resp = await self._http.post(url, headers=self._auth_headers(), json=body)
        if resp.status_code == 401:
            raise GmailAuthError(f"401 on POST {path}")
        resp.raise_for_status()
        return resp.json()

    async def send_message(self, raw: bytes, thread_id: str | None = None) -> dict:
        """Base64url-encode raw RFC-822 bytes and POST to Gmail send endpoint."""
        encoded = base64.urlsafe_b64encode(raw).decode("ascii")
        body: dict = {"raw": encoded}
        if thread_id:
            body["threadId"] = thread_id
        return await self._post("users/me/messages/send", body)

    async def list_history_since(self, start_history_id: str) -> list[dict]:
        """Paginate history records starting from start_history_id."""
        records: list[dict] = []
        page_token: str | None = None

        while True:
            params: dict = {
                "startHistoryId": start_history_id,
                "historyTypes": "messageAdded",
            }
            if page_token:
                params["pageToken"] = page_token

            data = await self._get("users/me/history", **params)
            records.extend(data.get("history", []))
            page_token = data.get("nextPageToken")
            if not page_token:
                break

        return records

    async def get_message(self, message_id: str) -> dict:
        """Fetch a full message and return a normalised dict."""
        data = await self._get(f"users/me/messages/{message_id}", format="full")
        return _parse_message(data)

    async def get_profile(self) -> dict:
        """Return the authenticated user's Gmail profile (includes historyId)."""
        return await self._get("users/me/profile")

    async def list_messages_since(self, start_date: "datetime") -> list[str]:
        """Return all Gmail message IDs after start_date via messages.list pagination.

        Uses the Gmail search query `after:YYYY/MM/DD` so only messages from
        start_date onward are included. Returns raw message IDs (not full messages).
        """
        q = f"after:{start_date.strftime('%Y/%m/%d')}"
        ids: list[str] = []
        page_token: str | None = None

        while True:
            params: dict = {"q": q, "maxResults": 500}
            if page_token:
                params["pageToken"] = page_token

            data = await self._get("users/me/messages", **params)
            for m in data.get("messages", []):
                if m.get("id"):
                    ids.append(m["id"])
            page_token = data.get("nextPageToken")
            if not page_token:
                break

        return ids



def _parse_message(data: dict) -> dict:
    payload = data.get("payload", {})
    headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}

    body_text, body_html = _extract_body(payload)
    date_str = headers.get("date", "")
    parsed_date = _parse_date(date_str)

    to_header = headers.get("to", "")
    cc_header = headers.get("cc", "")
    bcc_header = headers.get("bcc", "")
    to_email = _first_address(to_header)

    return {
        "headers": headers,
        "body_text": body_text,
        "body_html": body_html,
        "subject": headers.get("subject", ""),
        "from": _first_address(headers.get("from", "")),
        "to": to_email,
        "to_list": _parse_address_list(to_header),
        "cc": cc_header,
        "cc_list": _parse_address_list(cc_header),
        "bcc": bcc_header,
        "bcc_list": _parse_address_list(bcc_header),
        "message_id": headers.get("message-id", ""),
        "in_reply_to": headers.get("in-reply-to", ""),
        "references": headers.get("references", ""),
        "date": parsed_date,
        "thread_id": data.get("threadId", ""),
        "raw_payload": data,
    }


def _extract_body(payload: dict) -> tuple[str | None, str | None]:
    """Walk MIME parts and extract text/plain and text/html bodies."""
    mime = payload.get("mimeType", "")

    if mime == "text/plain":
        return _decode_body(payload), None
    if mime == "text/html":
        return None, _decode_body(payload)

    plain: str | None = None
    html_body: str | None = None
    for part in payload.get("parts", []):
        p, h = _extract_body(part)
        if p and plain is None:
            plain = p
        if h and html_body is None:
            html_body = h

    return plain, html_body


def _decode_body(part: dict) -> str | None:
    raw = part.get("body", {}).get("data", "")
    if not raw:
        return None
    try:
        return base64.urlsafe_b64decode(raw + "==").decode("utf-8", errors="replace")
    except Exception:
        return None


def _parse_date(date_str: str) -> datetime | None:
    if not date_str:
        return None
    try:
        return parsedate_to_datetime(date_str)
    except Exception:
        return None


def _first_address(addr_str: str) -> str:
    """Extract first email address from a comma-separated address header."""
    if not addr_str:
        return ""
    addrs = _parse_address_list(addr_str)
    return addrs[0] if addrs else ""


def _parse_address_list(addr_str: str) -> list[str]:
    """Parse a multi-recipient header into a list of bare email addresses.

    Uses Python's email.utils.getaddresses, which handles quoted display
    names containing commas and angle-bracket delimiters that the naive
    split-on-comma approach gets wrong (e.g. ``"Doe, Jane" <j@x.com>``).
    Empty or malformed entries are dropped; the returned list preserves
    header order so callers that care about position (e.g. To[0] for
    the from_email column on sent rows) still get deterministic output.
    """
    if not addr_str:
        return []
    out: list[str] = []
    for _name, addr in getaddresses([addr_str]):
        clean = (addr or "").strip()
        if clean and "@" in clean:
            out.append(clean)
    return out


def _parse_address_list(addr_str: str | None) -> list[str]:
    """Return all email addresses from a comma-separated address header.

    Handles both bare addresses (foo@bar.com) and display-name form
    (Display Name <foo@bar.com>). Returns an empty list for None/empty input.
    """
    if not addr_str:
        return []
    results: list[str] = []
    for raw in addr_str.split(","):
        part = raw.strip()
        if not part:
            continue
        if "<" in part and ">" in part:
            addr = part[part.index("<") + 1 : part.index(">")].strip()
        else:
            addr = part
        if addr:
            results.append(addr)
    return results


def _get_client_id() -> str:
    from src.config import settings
    return getattr(settings, "GOOGLE_CLIENT_ID", "")


def _get_client_secret() -> str:
    from src.config import settings
    return getattr(settings, "GOOGLE_CLIENT_SECRET", "")
