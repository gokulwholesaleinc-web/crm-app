"""Thin typed httpx clients — the C1 network seam (no business logic).

This is the ONLY place ingest touches the network. Mappers are pure functions
over the dicts these clients return, so the whole correctness layer is testable
without a network or a mock (the owner-waived no-mock seam per C1).

Design:
* One ``httpx.AsyncClient`` wrapper per platform shape, all sharing a single
  ``request_with_retry`` helper that honors ``Retry-After`` / Google
  ``RESOURCE_EXHAUSTED`` with exponential backoff + full jitter (D / A8).
* Errors are classified into exactly two typed buckets the health state machine
  (``health.py``) understands: :class:`TransientError` (429 / RESOURCE_EXHAUSTED /
  5xx / network) → backoff, no status change; :class:`PermanentError`
  (``invalid_grant`` / OAuth-190 / 4xx) → ``needs_reauth`` / ``error``.
* REST endpoints only — NO google-ads / google-analytics-data / grpc deps. GA4
  ``analyticsdata v1beta :runReport``; GSC ``webmasters v3 searchAnalytics:query``;
  Google Ads ``v20 …:searchStream``; PageSpeed ``pagespeedonline/v5`` (API key).
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Any, Protocol, runtime_checkable

import httpx

logger = logging.getLogger(__name__)

# REST bases (E5 version pins; verify at build — Ads v20 sunsets ~2026-06-10).
GA4_BASE = "https://analyticsdata.googleapis.com/v1beta"
GSC_BASE = "https://www.googleapis.com/webmasters/v3"
GOOGLE_ADS_BASE = "https://googleads.googleapis.com/v20"
PAGESPEED_URL = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"

_DEFAULT_TIMEOUT = httpx.Timeout(connect=10.0, read=60.0, write=30.0, pool=10.0)
_MAX_RETRIES = 4
_BASE_BACKOFF = 1.0  # seconds; doubled each attempt, then full-jittered
_MAX_BACKOFF = 60.0


class IngestHTTPError(Exception):
    """Base for any classified ingest HTTP failure."""

    def __init__(self, message: str, *, status_code: int | None = None, error_class: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        # Short stable token persisted to MarketingSyncRun.error_class / drives
        # the health classifier (e.g. "transient_429", "invalid_grant").
        self.error_class = error_class or type(self).__name__


class TransientError(IngestHTTPError):
    """Retryable: 429 / RESOURCE_EXHAUSTED / 5xx / network. Backoff, no disable (B5)."""


class PermanentError(IngestHTTPError):
    """Non-retryable: auth revocation, bad request, permission. Health acts now (B5)."""


class UnmappableShapeError(IngestHTTPError):
    """A 2xx payload whose STRUCTURE the mapper cannot recognize (CRITICAL-1).

    Distinct from a legitimately-empty result (E5 → ``[]``): this is raised only
    when the envelope itself is wrong — a renamed/absent top-level key, an error
    body where data was expected, or a row missing the structural fields the grain
    depends on. A drifted/degraded API shape that a mapper would otherwise map to
    ``[]`` and have recorded as ``success`` (freshness green, silent zero) instead
    raises this, and ``run_connection_sync`` records the run as ``partial`` — the
    data was NOT refreshed, and freshness stays truthful. Carries ``error_class``
    ``"unmappable_shape"``; the health machine treats it as a hard failure so
    persistent drift escalates rather than masquerading as a healthy zero.
    """

    def __init__(self, message: str, *, platform: str | None = None):
        super().__init__(message, error_class="unmappable_shape")
        self.platform = platform


def ensure_shape(ok: bool, message: str, *, platform: str | None = None) -> None:
    """Raise :class:`UnmappableShapeError` when a mapper's structural precondition
    fails. The single chokepoint mappers use to turn 'silent [] on drift' into a
    truthful ``partial`` run (CRITICAL-1)."""
    if not ok:
        raise UnmappableShapeError(message, platform=platform)


def _full_jitter_backoff(attempt: int, retry_after: float | None) -> float:
    """Exponential backoff with full jitter, honoring an explicit ``Retry-After``.

    ``attempt`` is 0-based. Result is ``max(retry_after, jitter(2**attempt * base))``
    capped at ``_MAX_BACKOFF`` so a hostile header can't pin us forever.
    """
    ceiling = min(_BASE_BACKOFF * (2**attempt), _MAX_BACKOFF)
    jittered = random.uniform(0, ceiling)  # full jitter (AWS architecture blog)
    floor = min(retry_after, _MAX_BACKOFF) if retry_after is not None else 0.0
    return max(floor, jittered)


def _parse_retry_after(response: httpx.Response) -> float | None:
    """Seconds from a ``Retry-After`` header (delta-seconds form only)."""
    raw = response.headers.get("Retry-After")
    if not raw:
        return None
    try:
        return float(raw.strip())
    except ValueError:
        return None  # HTTP-date form is ignored; jitter backoff still applies.


def _is_google_resource_exhausted(response: httpx.Response) -> bool:
    """Google REST surfaces quota as ``status: RESOURCE_EXHAUSTED`` (often 429)."""
    if response.status_code == 429:
        return True
    try:
        body = response.json()
    except (ValueError, httpx.DecodingError):
        return False
    err = body.get("error") if isinstance(body, dict) else None
    return bool(err) and err.get("status") == "RESOURCE_EXHAUSTED"


def _classify_oauth(response: httpx.Response) -> PermanentError | None:
    """Map a 400/401 body to a credential-revocation error (B5), else ``None``.

    * Google OAuth → ``error: "invalid_grant"`` (or ``UNAUTHENTICATED`` status).
    * Meta Graph → ``error.code == 190`` (``OAuthException``).
    """
    try:
        body = response.json()
    except (ValueError, httpx.DecodingError):
        return None
    if not isinstance(body, dict):
        return None
    err = body.get("error")
    # Google token endpoint shape: {"error": "invalid_grant", ...}
    if isinstance(err, str) and err in ("invalid_grant", "invalid_token"):
        return PermanentError(f"OAuth revoked: {err}", status_code=response.status_code, error_class="invalid_grant")
    if isinstance(err, dict):
        # Google API shape: {"error": {"status": "UNAUTHENTICATED", ...}}
        if err.get("status") in ("UNAUTHENTICATED", "PERMISSION_DENIED"):
            return PermanentError(
                f"Google auth/permission denied: {err.get('status')}",
                status_code=response.status_code,
                error_class="invalid_grant" if err.get("status") == "UNAUTHENTICATED" else "permission_denied",
            )
        # Meta Graph shape: {"error": {"code": 190, "type": "OAuthException", ...}}
        if err.get("code") == 190 or err.get("type") == "OAuthException":
            return PermanentError(
                "Meta OAuthException (code 190): token invalid/expired",
                status_code=response.status_code,
                error_class="oauth_exception_190",
            )
    return None


async def request_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Issue one request, retrying transient failures with jittered backoff.

    Returns the decoded JSON body on 2xx. Raises :class:`TransientError` only
    when retries are exhausted, or :class:`PermanentError` immediately for a
    classified auth/permission/bad-request failure (never retried).
    """
    last_transient: TransientError | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            response = await client.request(method, url, headers=headers, params=params, json=json)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last_transient = TransientError(f"network error: {exc}", error_class="network")
            await asyncio.sleep(_full_jitter_backoff(attempt, None))
            continue

        if response.is_success:
            try:
                return response.json()
            except (ValueError, httpx.DecodingError) as exc:
                # A 2xx with an unparseable body is a permanent contract break.
                raise PermanentError(f"unparseable success body: {exc}", status_code=response.status_code) from exc

        # quota / rate limit → transient with Retry-After
        if _is_google_resource_exhausted(response):
            last_transient = TransientError(
                "rate limited (429 / RESOURCE_EXHAUSTED)",
                status_code=response.status_code,
                error_class="transient_429",
            )
            await asyncio.sleep(_full_jitter_backoff(attempt, _parse_retry_after(response)))
            continue

        # auth revocation / permission → permanent, act immediately
        oauth = _classify_oauth(response)
        if oauth is not None:
            raise oauth

        if response.status_code >= 500:
            last_transient = TransientError(
                f"server error {response.status_code}",
                status_code=response.status_code,
                error_class="transient_5xx",
            )
            await asyncio.sleep(_full_jitter_backoff(attempt, _parse_retry_after(response)))
            continue

        # any other 4xx is a permanent client error (bad request, not found…)
        raise PermanentError(
            f"client error {response.status_code}: {response.text[:300]}",
            status_code=response.status_code,
            error_class=f"http_{response.status_code}",
        )

    assert last_transient is not None  # loop only exits here after a transient
    raise last_transient


@runtime_checkable
class GoogleSeam(Protocol):
    """The typed Google network seam (C1). ``GoogleClient`` is the production
    impl; a test injects a thin fixture-replay object satisfying the same shape —
    never a mock of business logic, only the HTTP boundary."""

    async def post(self, url: str, json: dict[str, Any], *, headers: dict[str, str] | None = None) -> dict[str, Any]: ...

    async def get(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]: ...


@runtime_checkable
class PageSpeedSeam(Protocol):
    """The typed PageSpeed network seam (C1)."""

    async def run(self, params: dict[str, Any]) -> dict[str, Any]: ...


class GoogleClient:
    """Bearer-auth REST client for GA4 / GSC / Google Ads (one OAuth access token).

    Google Ads additionally needs the ``developer-token`` and ``login-customer-id``
    headers; those are passed per-call so one client serves all three surfaces.
    """

    def __init__(self, access_token: str, *, client: httpx.AsyncClient | None = None):
        self._token = access_token
        self._client = client or httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)
        self._owns_client = client is None

    async def __aenter__(self) -> GoogleClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def _auth(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"}
        if extra:
            headers.update(extra)
        return headers

    async def post(self, url: str, json: dict[str, Any], *, headers: dict[str, str] | None = None) -> dict[str, Any]:
        return await request_with_retry(self._client, "POST", url, headers=self._auth(headers), json=json)

    async def get(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return await request_with_retry(self._client, "GET", url, headers=self._auth(), params=params)


class PageSpeedClient:
    """API-key-only client for PageSpeed Insights v5 (no OAuth, public URLs)."""

    def __init__(self, api_key: str | None = None, *, client: httpx.AsyncClient | None = None):
        self._api_key = api_key
        self._client = client or httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)
        self._owns_client = client is None

    async def __aenter__(self) -> PageSpeedClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def run(self, params: dict[str, Any]) -> dict[str, Any]:
        merged = dict(params)
        if self._api_key:
            merged["key"] = self._api_key
        return await request_with_retry(self._client, "GET", PAGESPEED_URL, params=merged)
