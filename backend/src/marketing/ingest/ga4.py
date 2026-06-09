"""GA4 ingest — analyticsdata v1beta :runReport fetcher + pure mapper.

REST against ``properties/{id}:runReport`` — NO ``google-analytics-data`` dep (C1).
Two query SHAPES land separately so A11 holds:

* **total** query — ``date`` dimension only → produces ``dimension_type='total'``
  rows. Account-level totals come ONLY from these (never summing dimension rows).
* **channel** query — ``date`` + ``sessionDefaultChannelGroup`` → traffic-source
  breakdown (``dimension_type='channel'``).

``map_ga4`` is PURE over one runReport payload + the ``dimension_type`` it was run
for. It detects ``samplingMetadatas`` → ``is_sampled=True`` on every row produced
(A11) so the read layer can disclose sampling. Empty rows → ``[]`` (E5 guard).
"""

from __future__ import annotations

import logging
from datetime import date as date_cls
from decimal import Decimal
from typing import Any

from ..money import q6
from ..rows import AnalyticsDailyRow
from .http_client import GA4_BASE, GoogleSeam, ensure_shape

logger = logging.getLogger(__name__)

_PAGE_LIMIT = 100000  # GA4 per-request row cap (D3)
_MAX_PAGES = 10  # bound the offset loop so a runaway property can't blow the quota

# Metrics requested for the total shape (engagement needs sessions+engaged).
_TOTAL_METRICS = [
    "sessions",
    "totalUsers",
    "newUsers",
    "engagedSessions",
    "engagementRate",
    "bounceRate",
    "keyEvents",
    "averageSessionDuration",
]
# Channel shape carries the same volume metrics minus the rate-of-whole ones.
_CHANNEL_METRICS = ["sessions", "totalUsers", "newUsers", "engagedSessions"]


def _date_dim() -> dict[str, str]:
    return {"name": "date"}


def _body(metrics: list[str], dimensions: list[dict[str, str]], window_start: date_cls, window_end: date_cls) -> dict[str, Any]:
    return {
        "dimensions": dimensions,
        "metrics": [{"name": m} for m in metrics],
        "dateRanges": [{"startDate": window_start.isoformat(), "endDate": window_end.isoformat()}],
        "keepEmptyRows": False,
        # Deterministic order so offset paging (_run_paged) is stable across pages —
        # GA4 doesn't guarantee row order without an explicit orderBys (date is always
        # a selected dimension here).
        "orderBys": [{"dimension": {"dimensionName": "date"}}],
        "limit": _PAGE_LIMIT,
        # H8: ask GA4 to report its token-bucket consumption so backfills can be
        # paced against the property quota instead of only reacting to 429s.
        "returnPropertyQuota": True,
    }


async def _run_paged(client: GoogleSeam, url: str, body: dict[str, Any]) -> dict[str, Any]:
    """Run a runReport, following ``offset`` until a short page (H4).

    GA4 caps a request at ``limit`` rows; the previous code issued ONE request and
    a comment falsely claimed offset paging, silently truncating >100k-row pulls.
    This accumulates all pages (bounded by ``_MAX_PAGES``) and keeps the first
    page's headers/metadata so the mapper's A11 sampling/golden detection still
    works. The first page's ``propertyQuota`` is logged (H8).
    """
    first: dict[str, Any] | None = None
    all_rows: list[dict[str, Any]] = []
    offset = 0
    for _ in range(_MAX_PAGES):
        page = await client.post(url, {**body, "offset": offset})
        if first is None:
            # Validate at the fetch boundary (CRITICAL-1): a valid runReport always
            # carries report structure (headers/metadata) even with zero rows; a 2xx
            # error/renamed body has none. Raise here so the merge below (which injects
            # a 'rows' key) can't mask the drift from the mapper guard → silent zero.
            ensure_shape(
                isinstance(page, dict)
                and any(k in page for k in ("rows", "dimensionHeaders", "metricHeaders", "metadata")),
                "ga4 runReport: unrecognized response envelope",
                platform="ga4",
            )
            first = page
            quota = page.get("propertyQuota") if isinstance(page, dict) else None
            if quota:
                logger.info("[ga4] propertyQuota %s", quota)
        rows = page.get("rows") or [] if isinstance(page, dict) else []
        all_rows.extend(rows)
        if len(rows) < _PAGE_LIMIT:
            break
        offset += _PAGE_LIMIT
    if first is None:  # no pages returned at all
        return {"rows": []}
    merged = dict(first)
    merged["rows"] = all_rows
    return merged


async def fetch_ga4_total(
    client: GoogleSeam, *, property_id: str, window_start: date_cls, window_end: date_cls
) -> dict[str, Any]:
    """Fetch the date-only (total) runReport — the A11 source of truth for totals."""
    url = f"{GA4_BASE}/properties/{property_id}:runReport"
    return await _run_paged(client, url, _body(_TOTAL_METRICS, [_date_dim()], window_start, window_end))


async def fetch_ga4_channels(
    client: GoogleSeam, *, property_id: str, window_start: date_cls, window_end: date_cls
) -> dict[str, Any]:
    """Fetch the date × channel runReport (traffic-source breakdown), offset-paged."""
    url = f"{GA4_BASE}/properties/{property_id}:runReport"
    dims = [_date_dim(), {"name": "sessionDefaultChannelGroup"}]
    return await _run_paged(client, url, _body(_CHANNEL_METRICS, dims, window_start, window_end))


def _is_sampled(payload: dict[str, Any]) -> bool:
    """Any non-empty ``samplingMetadatas`` on the report means it was sampled (A11)."""
    metas = payload.get("metadata", {}).get("samplingMetadatas")
    return bool(metas)


def _is_data_golden(payload: dict[str, Any]) -> bool:
    """False when the report had a high-cardinality "(other)" overflow or was not
    yet finalized (H3). GA4 sets ``metadata.dataLossFromOtherRow=true`` when a
    breakdown overflowed into a lumped "(other)" row (so it won't tie out to the
    totals), and ``metadata.dataGolden=false`` while the day is still processing.
    GA4 OMITS ``dataGolden`` when the data IS golden, so a missing key = golden."""
    meta = payload.get("metadata", {}) or {}
    if meta.get("dataLossFromOtherRow"):
        return False
    return meta.get("dataGolden", True) is not False


def _dim_index(payload: dict[str, Any], name: str) -> int | None:
    for i, header in enumerate(payload.get("dimensionHeaders", []) or []):
        if header.get("name") == name:
            return i
    return None


def _metric_index_map(payload: dict[str, Any]) -> dict[str, int]:
    return {h.get("name"): i for i, h in enumerate(payload.get("metricHeaders", []) or [])}


def _int(values: list[dict], idx: int | None) -> int | None:
    if idx is None:
        return None
    raw = values[idx].get("value")
    return int(float(raw)) if raw not in (None, "") else None


def _dec(values: list[dict], idx: int | None) -> Decimal | None:
    if idx is None:
        return None
    raw = values[idx].get("value")
    return q6(raw) if raw not in (None, "") else None


def map_ga4(
    payload: dict[str, Any],
    *,
    connection_id: int,
    company_id: int,
    dimension_type: str,
) -> list[AnalyticsDailyRow]:
    """Pure: one runReport payload → ``AnalyticsDailyRow``s for one dimension type.

    ``dimension_type`` is ``'total'`` (date-only shape) or ``'channel'`` (date ×
    channel). Totals are produced ONLY from the total shape — this mapper never
    sums dimension rows to fabricate a total (A11). Sampling is propagated to
    every emitted row. Empty payload → ``[]`` (E5 guard).
    """
    # Envelope guard (CRITICAL-1): a valid runReport always carries report
    # structure (headers/metadata) even with zero traffic. A payload with none of
    # those is an error body / drifted shape, not a genuinely-empty report — raise
    # so the run is 'partial' rather than a silent zero recorded as success.
    ensure_shape(
        isinstance(payload, dict)
        and any(k in payload for k in ("rows", "dimensionHeaders", "metricHeaders", "metadata")),
        "ga4 payload missing runReport structure (headers/metadata)",
        platform="ga4",
    )

    rows: list[AnalyticsDailyRow] = []
    raw_rows = payload.get("rows") or []
    if not raw_rows:
        return rows

    sampled = _is_sampled(payload)
    golden = _is_data_golden(payload)
    date_idx = _dim_index(payload, "date")
    channel_idx = _dim_index(payload, "sessionDefaultChannelGroup")
    mi = _metric_index_map(payload)

    for raw in raw_rows:
        dims = raw.get("dimensionValues", [])
        mets = raw.get("metricValues", [])
        if date_idx is None:
            continue
        row_date = date_cls.fromisoformat(_ga4_date(dims[date_idx].get("value", "")))

        dimension_value = ""
        if dimension_type == "channel" and channel_idx is not None:
            dimension_value = dims[channel_idx].get("value", "") or "(not set)"

        rows.append(
            AnalyticsDailyRow(
                connection_id=connection_id,
                company_id=company_id,
                source="ga4",
                date=row_date,
                dimension_type=dimension_type,
                dimension_value=dimension_value,
                sessions=_int(mets, mi.get("sessions")),
                users=_int(mets, mi.get("totalUsers")),
                new_users=_int(mets, mi.get("newUsers")),
                engaged_sessions=_int(mets, mi.get("engagedSessions")),
                engagement_rate=_dec(mets, mi.get("engagementRate")),
                bounce_rate=_dec(mets, mi.get("bounceRate")),
                key_events=_dec(mets, mi.get("keyEvents")),
                # H7: keyEvents IS GA4's conversion metric and is carried in
                # key_events ONLY — NOT duplicated into `conversions` (that column is
                # for ad-platform conversions; duplicating conflated two different
                # metrics and invited a double-count). Reads display key_events for GA4.
                conversions=None,
                avg_session_duration=_dec(mets, mi.get("averageSessionDuration")),
                is_sampled=sampled,
                is_data_golden=golden,
            )
        )

    return rows


def _ga4_date(raw: str) -> str:
    """GA4 ``date`` dimension is ``YYYYMMDD`` — expand to ISO ``YYYY-MM-DD``."""
    if len(raw) == 8 and raw.isdigit():
        return f"{raw[0:4]}-{raw[4:6]}-{raw[6:8]}"
    return raw
