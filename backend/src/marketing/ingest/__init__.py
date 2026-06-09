"""Marketing ingest orchestration — the write path for ONE connection.

``run_connection_sync`` is the single entry point the scheduler hook and the
"refresh now" endpoint both call. For one ``PlatformConnection`` it:

1. acquires the per-connection advisory lock (``warehouse.lock_connection``, D2) so
   daily / settling / backfill lanes can't interleave on the same rows;
2. writes a credential-access audit row (``MarketingCredentialAudit``, B1) — the
   token value is NEVER recorded;
3. decrypts the access token (``crypto.decrypt_token``), dispatches to the
   platform fetcher (the C1 network seam), lands the raw payload
   (``warehouse.insert_raw_payload``), maps it with the PURE mapper, and upserts
   facts/dims via ``warehouse.*``;
4. records a ``MarketingSyncRun`` (status / rows_upserted / window / error /
   error_class) and transitions connection health (``health.py``, B5).

The whole body is wrapped so one connection's failure becomes a recorded
``error``/``needs_reauth`` row and never propagates — mirroring the scheduler's
per-account isolation (``core/scheduler.py:_sync_google_calendars``). Callers that
fan out over many connections each get their own fresh session so a rollback in
one can't poison another (the caller owns that loop; see the module docstring of
``health.py`` and the plan's D1/D2).
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from .. import crypto, warehouse
from ..models import MarketingCredentialAudit, MarketingSyncRun, PlatformConnection
from . import ga4, google_ads, gsc, health, pagespeed
from .http_client import (
    GoogleClient,
    GoogleSeam,
    IngestHTTPError,
    PageSpeedClient,
    PageSpeedSeam,
    PermanentError,
    UnmappableShapeError,
)

logger = logging.getLogger(__name__)

# Platforms this slice ingests (Phase 1 = Google-only; Meta/social ship dark).
SUPPORTED_PLATFORMS = frozenset({"google_ads", "ga4", "gsc", "pagespeed"})


class IngestConfigError(PermanentError):
    """A connection is missing config required to sync (token, account id, key).

    Subclasses ``PermanentError`` so the health machine treats a misconfigured
    connection as a hard failure, not an endless transient retry.
    """


async def _write_audit(
    session: AsyncSession, connection: PlatformConnection, *, action: str, detail: str | None = None
) -> None:
    """Append a credential-access audit row (B1) — never the token value."""
    session.add(
        MarketingCredentialAudit(
            connection_id=connection.id,
            company_id=connection.company_id,
            platform=connection.platform,
            actor_type="ingest",
            action=action,
            detail=detail,
        )
    )
    await session.flush()


def _access_token(connection: PlatformConnection) -> str:
    """Decrypt the stored access token (fail-closed via ``crypto``)."""
    if not connection.access_token_ciphertext:
        raise IngestConfigError(
            f"connection {connection.id} has no access token", error_class="missing_token"
        )
    return crypto.decrypt_token(connection.access_token_ciphertext)


async def _dispatch(
    session: AsyncSession,
    connection: PlatformConnection,
    *,
    run_type: str,
    window_start: date,
    window_end: date,
    http_client: Any | None,
) -> int:
    """Fetch → land raw → map → upsert for one platform. Returns rows upserted.

    Delegates to a per-platform handler so each owns its own typed seam; injecting
    ``http_client`` keeps the orchestrator testable without the network (C1) while
    never mocking business logic. When ``None``, a real client is constructed from
    the connection's decrypted credentials inside the handler. ``run_type`` lets a
    handler vary by lane (e.g. the settling re-fetch skips the ad-group grain, A7).
    """
    handler = _HANDLERS.get(connection.platform)
    if handler is None:
        raise IngestConfigError(
            f"unsupported platform '{connection.platform}'", error_class="unsupported_platform"
        )
    return await handler(session, connection, run_type, window_start, window_end, http_client)


def _google_seam(connection: PlatformConnection, http_client: Any | None) -> GoogleSeam:
    return http_client if http_client is not None else GoogleClient(_access_token(connection))


def _pagespeed_seam(http_client: Any | None) -> PageSpeedSeam:
    return http_client if http_client is not None else PageSpeedClient(_pagespeed_api_key())


async def _sync_google_ads(
    session: AsyncSession, connection: PlatformConnection,
    run_type: str, window_start: date, window_end: date, http_client: Any | None,
) -> int:
    client = _google_seam(connection, http_client)
    dev_token = _require(connection, _ads_developer_token(), "developer token")
    # A7: the settling re-fetch is conversion-scoped — re-pull only the
    # campaign/account grain over the conversion window, NOT the heavier ad-group
    # grain (which the daily 3-day lookback already restates for recent days).
    include_adgroups = run_type != "settling"
    payload = await google_ads.fetch_google_ads(
        client,
        customer_id=connection.external_account_id,
        developer_token=dev_token,
        login_customer_id=connection.manager_account_id,
        window_start=window_start,
        window_end=window_end,
        include_adgroups=include_adgroups,
    )
    await warehouse.insert_raw_payload(
        session, connection_id=connection.id, platform="google_ads", endpoint="googleAds:searchStream",
        window_start=window_start, window_end=window_end,
        request_fingerprint=f"ads:{connection.external_account_id}:{window_start}:{window_end}",
        payload=payload,
    )
    ads, campaigns, adgroups = google_ads.map_google_ads(
        payload, connection_id=connection.id, company_id=connection.company_id, currency=connection.currency
    )
    rows = await warehouse.upsert_ads_daily(session, ads)
    await warehouse.upsert_campaigns(session, campaigns)
    await warehouse.upsert_adgroups(session, adgroups)
    return rows


async def _sync_ga4(
    session: AsyncSession, connection: PlatformConnection,
    run_type: str, window_start: date, window_end: date, http_client: Any | None,
) -> int:
    client = _google_seam(connection, http_client)
    cid, company = connection.id, connection.company_id
    total = await ga4.fetch_ga4_total(
        client, property_id=connection.external_account_id, window_start=window_start, window_end=window_end
    )
    channels = await ga4.fetch_ga4_channels(
        client, property_id=connection.external_account_id, window_start=window_start, window_end=window_end
    )
    for shape, payload in (("total", total), ("channel", channels)):
        await warehouse.insert_raw_payload(
            session, connection_id=cid, platform="ga4", endpoint=f"runReport:{shape}",
            window_start=window_start, window_end=window_end,
            request_fingerprint=f"ga4:{shape}:{connection.external_account_id}:{window_start}:{window_end}",
            payload=payload,
        )
    analytics = ga4.map_ga4(total, connection_id=cid, company_id=company, dimension_type="total")
    analytics += ga4.map_ga4(channels, connection_id=cid, company_id=company, dimension_type="channel")
    return await warehouse.upsert_analytics_daily(session, analytics)


async def _sync_gsc(
    session: AsyncSession, connection: PlatformConnection,
    run_type: str, window_start: date, window_end: date, http_client: Any | None,
) -> int:
    client = _google_seam(connection, http_client)
    payload = await gsc.fetch_gsc(
        client, site_url=connection.external_account_id, window_start=window_start, window_end=window_end
    )
    await warehouse.insert_raw_payload(
        session, connection_id=connection.id, platform="gsc", endpoint="searchAnalytics:query",
        window_start=window_start, window_end=window_end,
        request_fingerprint=f"gsc:{connection.external_account_id}:{window_start}:{window_end}",
        payload=payload,
    )
    analytics = gsc.map_gsc(payload, connection_id=connection.id, company_id=connection.company_id)
    return await warehouse.upsert_analytics_daily(session, analytics)


async def _sync_pagespeed(
    session: AsyncSession, connection: PlatformConnection,
    run_type: str, window_start: date, window_end: date, http_client: Any | None,
) -> int:
    client = _pagespeed_seam(http_client)
    url = connection.display_name or connection.external_account_id
    total = 0
    for strategy in ("mobile", "desktop"):
        payload = await pagespeed.fetch_pagespeed(client, url=url, strategy=strategy)
        await warehouse.insert_raw_payload(
            session, connection_id=connection.id, platform="pagespeed", endpoint=f"runPagespeed:{strategy}",
            window_start=window_start, window_end=window_end,
            request_fingerprint=f"pagespeed:{strategy}:{url}:{window_end}",
            payload=payload,
        )
        snapshots = pagespeed.map_pagespeed(
            payload, connection_id=connection.id, company_id=connection.company_id,
            captured_date=window_end, strategy=strategy,
        )
        total += await warehouse.upsert_site_health(session, snapshots)
    return total


# platform → handler; the only place that knows the per-platform fetch/map/upsert.
_HANDLERS = {
    "google_ads": _sync_google_ads,
    "ga4": _sync_ga4,
    "gsc": _sync_gsc,
    "pagespeed": _sync_pagespeed,
}


def _require(connection: PlatformConnection, value: str | None, what: str) -> str:
    if not value:
        raise IngestConfigError(
            f"connection {connection.id} ({connection.platform}) missing {what}",
            error_class="missing_config",
        )
    return value


def _ads_developer_token() -> str | None:
    from src.config import settings

    return settings.GOOGLE_ADS_DEVELOPER_TOKEN or None


def _pagespeed_api_key() -> str | None:
    from src.config import settings

    return settings.PAGESPEED_API_KEY or None


async def run_connection_sync(
    session: AsyncSession,
    connection: PlatformConnection,
    *,
    run_type: str,
    window_start: date,
    window_end: date,
    http_client: Any | None = None,
) -> MarketingSyncRun:
    """Run ONE connection's ingest end-to-end; always returns a ``MarketingSyncRun``.

    Never raises for a per-connection failure — the failure is captured on the
    returned run row (``status='error'``, ``error``/``error_class``) and the
    connection's health is transitioned (B5). The caller commits.

    ``http_client`` lets a test inject a pre-seeded network seam; in production it
    is ``None`` and built from the connection's decrypted credentials.
    """
    run = MarketingSyncRun(
        connection_id=connection.id,
        company_id=connection.company_id,
        platform=connection.platform,
        run_type=run_type,
        status="running",
        window_start=window_start,
        window_end=window_end,
        rows_upserted=0,
    )
    session.add(run)
    await session.flush()

    try:
        if connection.platform not in SUPPORTED_PLATFORMS:
            raise IngestConfigError(
                f"platform '{connection.platform}' not ingestible in this slice",
                error_class="unsupported_platform",
            )
        # D2: serialize this connection's writers (daily/settling/backfill).
        await warehouse.lock_connection(session, connection.id)
        await _write_audit(
            session, connection, action="access",
            detail=f"{run_type} {window_start}..{window_end}",
        )
        rows = await _dispatch(
            session, connection, run_type=run_type,
            window_start=window_start, window_end=window_end, http_client=http_client,
        )
        run.rows_upserted = rows
        run.status = "success"
        health.apply_success(connection)
    except UnmappableShapeError as exc:
        # CRITICAL-1: the API returned 2xx but the mapper could not recognize the
        # shape (drifted/degraded). The mapper aborted BEFORE any upsert, so the
        # facts were NOT refreshed. Record 'partial' (truthful — distinct from a
        # 'success' silent zero and from an 'error' fetch failure) and let health
        # count it (apply_failure does NOT stamp last_synced_at, so freshness stays
        # honest and persistent drift escalates).
        health.apply_failure(connection, exc)
        run.status = "partial"
        run.error = str(exc)[:2000]
        run.error_class = "unmappable_shape"
        logger.warning(
            "[marketing_ingest] connection=%s platform=%s unmappable shape (partial): %s",
            connection.id, connection.platform, exc,
        )
    except Exception as exc:  # noqa: BLE001 — isolation boundary (mirrors scheduler)
        outcome = health.apply_failure(connection, exc)
        run.status = "error"
        run.error = str(exc)[:2000]
        run.error_class = health.error_class_for_run(exc)
        if isinstance(exc, IngestHTTPError):
            logger.warning(
                "[marketing_ingest] connection=%s platform=%s %s: %s",
                connection.id, connection.platform, outcome.value, exc,
            )
        else:
            # Unexpected (mapper/DB bug) — keep the full traceback.
            logger.exception(
                "[marketing_ingest] connection=%s platform=%s unexpected failure",
                connection.id, connection.platform,
            )
    finally:
        run.finished_at = datetime.now(UTC)
        await session.flush()

    return run
