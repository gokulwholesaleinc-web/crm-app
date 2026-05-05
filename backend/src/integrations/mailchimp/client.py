"""Async HTTP client for the Mailchimp Marketing API v3.0.

Mailchimp uses HTTP Basic auth where the password is the API key. The
key carries a ``-<dc>`` suffix (e.g. ``...-us19``) that selects the
data-center subdomain — we expect callers to split it once at connect
time and pass ``server_prefix`` separately so the URL doesn't have to
be reparsed on every request.

This module is a thin transport layer; high-level orchestration lives
in :mod:`src.integrations.mailchimp.service`.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = httpx.Timeout(10.0, connect=5.0)


class MailchimpError(Exception):
    """Raised when Mailchimp returns a non-2xx response."""

    def __init__(self, status_code: int, body: dict[str, Any] | str):
        self.status_code = status_code
        self.body = body
        detail = body.get("detail") if isinstance(body, dict) else str(body)
        super().__init__(f"Mailchimp HTTP {status_code}: {detail}")


def split_api_key(api_key: str) -> tuple[str, str]:
    """Return ``(api_key, server_prefix)`` from a raw Mailchimp key.

    Mailchimp's keys end in ``-<dc>``; the dc is also the API
    subdomain. Raises :class:`ValueError` if the suffix is absent so we
    don't silently default to the wrong data center.
    """
    if "-" not in api_key:
        raise ValueError("Mailchimp API key must end with a -<dc> suffix (e.g. -us19)")
    _, server_prefix = api_key.rsplit("-", 1)
    if not server_prefix:
        raise ValueError("Mailchimp API key has empty data-center suffix")
    return api_key, server_prefix


def subscriber_hash(email: str) -> str:
    """MD5 of the lowercase email — Mailchimp's subscriber-id form."""
    return hashlib.md5(email.strip().lower().encode("utf-8")).hexdigest()  # noqa: S324


class MailchimpClient:
    """Minimal async wrapper over the Mailchimp Marketing API.

    Use as an async context manager so the underlying
    :class:`httpx.AsyncClient` is closed cleanly::

        async with MailchimpClient(api_key, server_prefix) as mc:
            await mc.ping()

    The :class:`httpx.AsyncClient` may also be injected for tests via
    the ``transport`` argument (passed through to ``httpx.AsyncClient``).
    """

    def __init__(
        self,
        api_key: str,
        server_prefix: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: httpx.Timeout = DEFAULT_TIMEOUT,
    ):
        if not server_prefix:
            raise ValueError("server_prefix is required")
        self._base_url = f"https://{server_prefix}.api.mailchimp.com/3.0"
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            auth=("anystring", api_key),
            timeout=timeout,
            transport=transport,
        )

    async def __aenter__(self) -> MailchimpClient:
        return self

    async def __aexit__(self, *exc) -> None:
        await self._client.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, path: str, **kwargs) -> dict[str, Any]:
        resp = await self._client.request(method, path, **kwargs)
        if resp.status_code >= 400:
            try:
                body = resp.json()
            except ValueError:
                body = resp.text
            raise MailchimpError(resp.status_code, body)
        if resp.status_code == 204 or not resp.content:
            return {}
        return resp.json()

    # --- Account ---------------------------------------------------

    async def ping(self) -> dict[str, Any]:
        """Lightweight health check; returns ``{"health_status": "..."}``."""
        return await self._request("GET", "/ping")

    async def get_account(self) -> dict[str, Any]:
        """Account root — login.email, account_id, etc."""
        return await self._request("GET", "/")

    # --- Audiences (Lists) ----------------------------------------

    async def list_audiences(
        self, *, count: int = 100, offset: int = 0
    ) -> dict[str, Any]:
        return await self._request(
            "GET",
            "/lists",
            params={"count": count, "offset": offset},
        )

    async def get_audience(self, list_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/lists/{list_id}")

    # --- Members --------------------------------------------------

    async def upsert_member(
        self,
        list_id: str,
        email: str,
        *,
        status_if_new: str = "subscribed",
        merge_fields: dict[str, Any] | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Idempotent add-or-update by email.

        ``status_if_new`` only applies on first insert — existing
        members keep whatever subscription state they had, so we never
        re-subscribe someone who has already opted out.
        """
        payload: dict[str, Any] = {
            "email_address": email,
            "status_if_new": status_if_new,
        }
        if merge_fields:
            payload["merge_fields"] = merge_fields
        if tags:
            payload["tags"] = tags
        return await self._request(
            "PUT",
            f"/lists/{list_id}/members/{subscriber_hash(email)}",
            json=payload,
        )

    async def get_member(self, list_id: str, email: str) -> dict[str, Any]:
        return await self._request(
            "GET", f"/lists/{list_id}/members/{subscriber_hash(email)}"
        )

    # --- Campaigns ------------------------------------------------

    async def create_regular_campaign(
        self,
        *,
        list_id: str,
        subject: str,
        from_name: str,
        reply_to: str,
        title: str | None = None,
    ) -> dict[str, Any]:
        payload = {
            "type": "regular",
            "recipients": {"list_id": list_id},
            "settings": {
                "subject_line": subject,
                "from_name": from_name,
                "reply_to": reply_to,
                "title": title or subject,
            },
        }
        return await self._request("POST", "/campaigns", json=payload)

    async def set_campaign_content(
        self, campaign_id: str, *, html: str
    ) -> dict[str, Any]:
        return await self._request(
            "PUT", f"/campaigns/{campaign_id}/content", json={"html": html}
        )

    async def send_campaign(self, campaign_id: str) -> dict[str, Any]:
        return await self._request(
            "POST", f"/campaigns/{campaign_id}/actions/send"
        )

    async def get_campaign(self, campaign_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/campaigns/{campaign_id}")

    # --- Reports --------------------------------------------------

    async def get_report(self, campaign_id: str) -> dict[str, Any]:
        """Aggregate report — opens, clicks, bounces, unsubscribes."""
        return await self._request("GET", f"/reports/{campaign_id}")
