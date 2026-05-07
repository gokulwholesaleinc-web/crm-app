"""Low-level Gmail API client — no FastAPI dependencies, no routes."""

import base64
import logging
import re
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

    async def list_send_as(self) -> list[str]:
        """Return verified send-as addresses (lowercased).

        Returns [] only on a 403 — non-Workspace accounts can lack the
        capability even with gmail.readonly granted. Auth + transient
        errors propagate so callers don't clobber last-known-good aliases
        with [] when Gmail blips.
        """
        try:
            data = await self._get("users/me/settings/sendAs")
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 403:
                logger.info(
                    "[gmail.list_send_as] 403 for user_id=%s — account lacks sendAs capability",
                    self._conn.user_id,
                )
                return []
            raise

        out: list[str] = []
        seen: set[str] = set()
        for entry in data.get("sendAs") or []:
            status = entry.get("verificationStatus")
            is_primary = bool(entry.get("isPrimary"))
            if status != "accepted" and not (status is None and is_primary):
                continue
            addr = (entry.get("sendAsEmail") or "").strip().lower()
            if addr and addr not in seen:
                seen.add(addr)
                out.append(addr)
        return out

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
    attachments = _walk_attachments(payload)

    # Substitute Content-ID references in the HTML body with inline data URIs
    # so the browser can actually render embedded images. Without this, the
    # canonical Gmail HTML email — which references its inline logo/photo
    # attachments via <img src="cid:..."> — renders as broken-image icons
    # in the EmailThread view. Falls back to the original HTML on any
    # decode error (we'd rather show the surrounding text than nothing).
    if body_html:
        try:
            body_html = _inline_cid_images(body_html, attachments)
        except Exception as exc:
            logger.warning(
                "[gmail_parse] inline-cid substitution failed for message %s: %s",
                data.get("id"),
                exc,
            )

    date_str = headers.get("date", "")
    parsed_date = _parse_date(date_str)

    to_header = headers.get("to", "")
    cc_header = headers.get("cc", "")
    bcc_header = headers.get("bcc", "")
    to_email = _first_address(to_header)

    # Strip the inline-only image data from the persisted attachment list
    # — once it's substituted into the HTML body we don't need to keep a
    # second copy on the row. Non-inline attachments (cid is None) keep
    # their metadata so a future "download attachment" UI has what it
    # needs to fetch from Gmail on demand.
    attachments_meta = [
        {
            "filename": a["filename"],
            "mime_type": a["mime_type"],
            "size": a["size"],
            "attachment_id": a["attachment_id"],
            "is_inline": a["cid"] is not None,
        }
        for a in attachments
        if (a["filename"] or a["cid"]) and a["mime_type"]
    ]

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
        "attachments": attachments_meta,
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


# Cap individual inline images at ~2.5MB raw bytes to keep email rows
# from ballooning past sane Postgres TOAST thresholds. Anything bigger
# almost certainly came from a sender's photo attachment, not a
# logo/banner — if we ever need those, we'll pull them on demand from
# Gmail by attachment_id rather than embed.
_MAX_INLINE_IMAGE_BYTES = 2_500_000


def _walk_attachments(payload: dict) -> list[dict]:
    """Walk every leaf MIME part and harvest attachment metadata.

    Returns one entry per non-multipart, non-text part. Each entry has::

        {
            "mime_type": "image/png",
            "filename": "logo.png" | "",
            "cid":      "image001@1234.5678" | None,
            "size":     12345,
            "data":     "<base64url body>" | None,   # only for small,
                                                     # inline payloads
            "attachment_id": "ANGjdJ..." | None,     # for fetch-on-demand
        }

    Inline images (those with a Content-ID header) keep their decoded
    bytes via the ``data`` field so the caller can substitute them
    into the HTML body. Non-inline attachments have ``data=None`` and
    rely on the ``attachment_id`` for a separate Gmail API call.
    """
    out: list[dict] = []

    def visit(part: dict) -> None:
        mime = part.get("mimeType", "") or ""
        if mime.startswith("multipart/"):
            for child in part.get("parts", []):
                visit(child)
            return
        if mime.startswith("text/"):
            # text/plain + text/html are handled by _extract_body; skip.
            return
        body = part.get("body", {}) or {}
        if not (body.get("data") or body.get("attachmentId")):
            return  # empty/structural part — nothing to harvest
        headers = {
            (h.get("name") or "").lower(): h.get("value") or ""
            for h in (part.get("headers") or [])
        }
        cid_raw = headers.get("content-id", "").strip()
        cid = cid_raw.strip("<>") or None
        out.append(
            {
                "mime_type": mime,
                "filename": part.get("filename") or "",
                "cid": cid,
                "size": int(body.get("size") or 0),
                "data": body.get("data"),
                "attachment_id": body.get("attachmentId"),
            }
        )

    visit(payload)
    return out


# Two regexes because real-world senders emit BOTH quoted and unquoted
# cid: refs:
#   <img src="cid:logo">   ← Gmail web compose, most clients
#   <img src=cid:logo>     ← Outlook on Windows + some Apple Mail variants
# A single regex with optional quotes is hard to bound (the unquoted
# terminator is `whitespace|>` rather than the same quote), so we keep
# two simple patterns and run both through .sub.
_CID_SRC_RE_QUOTED = re.compile(
    r"""(src|background)\s*=\s*(['"])cid:([^'"]+)\2""",
    re.IGNORECASE,
)
_CID_SRC_RE_UNQUOTED = re.compile(
    r"""(src|background)\s*=\s*cid:([^\s>]+)""",
    re.IGNORECASE,
)


def _inline_cid_images(html: str, attachments: list[dict]) -> str:
    """Replace ``<img src="cid:...">`` with embedded ``data:`` URIs.

    Only inline images whose payload is already in the message (``data``
    field set, image/* mime type, under the size cap) are substituted.
    Everything else stays as ``cid:...`` — those references still won't
    render, but at least the HTML structure is preserved and the broken-
    image icon is honest.

    Handles both quoted and unquoted ``src=cid:`` syntaxes — Outlook on
    Windows and some Apple Mail variants emit the unquoted form, which
    a quoted-only matcher would silently leave broken (the rehydrate
    endpoint then re-fetches them and can't tell the regex didn't match
    vs. the attachment is missing — see PR follow-up).
    """
    if not html or not attachments:
        return html

    cid_to_data_uri: dict[str, str] = {}
    for att in attachments:
        cid = att.get("cid")
        mime = att.get("mime_type") or ""
        raw_b64 = att.get("data")
        size = att.get("size") or 0
        if not (cid and raw_b64 and mime.startswith("image/")):
            continue
        if size > _MAX_INLINE_IMAGE_BYTES:
            continue
        try:
            decoded = base64.urlsafe_b64decode(raw_b64 + "==")
        except Exception as exc:  # noqa: BLE001 — defensive on hostile inputs
            logger.warning(
                "[inline_cid] base64 decode failed cid=%s mime=%s: %s",
                cid, mime, exc,
            )
            continue
        if len(decoded) > _MAX_INLINE_IMAGE_BYTES:
            continue
        std_b64 = base64.b64encode(decoded).decode("ascii")
        key = cid.lower()
        # RFC 2392 forbids duplicate Content-IDs but real senders do it.
        # Last-wins keeps the existing behavior; the warning surfaces
        # the case so the next "wrong logo" report has a breadcrumb.
        if key in cid_to_data_uri:
            logger.info("[inline_cid] duplicate cid=%s — last-wins", cid)
        cid_to_data_uri[key] = f"data:{mime};base64,{std_b64}"

    if not cid_to_data_uri:
        return html

    def replace_quoted(match: re.Match[str]) -> str:
        attr = match.group(1)
        quote = match.group(2)
        cid = match.group(3).strip().lower()
        uri = cid_to_data_uri.get(cid)
        if not uri:
            return match.group(0)
        return f"{attr}={quote}{uri}{quote}"

    def replace_unquoted(match: re.Match[str]) -> str:
        attr = match.group(1)
        cid = match.group(2).strip().lower()
        uri = cid_to_data_uri.get(cid)
        if not uri:
            return match.group(0)
        # Re-emit as quoted form so downstream HTML stays well-formed
        # even if the substituted data: URI contains an attribute-
        # boundary char.
        return f'{attr}="{uri}"'

    html = _CID_SRC_RE_QUOTED.sub(replace_quoted, html)
    html = _CID_SRC_RE_UNQUOTED.sub(replace_unquoted, html)
    return html


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


def _get_client_id() -> str:
    from src.config import settings
    return getattr(settings, "GOOGLE_CLIENT_ID", "")


def _get_client_secret() -> str:
    from src.config import settings
    return getattr(settings, "GOOGLE_CLIENT_SECRET", "")
