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

from datetime import date as date_cls
from decimal import Decimal
from typing import Any

from ..money import q6
from ..rows import AnalyticsDailyRow
from .http_client import GA4_BASE, GoogleSeam, ensure_shape

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
        "limit": 100000,  # GA4 per-request cap (D3); paged on offset for bigger pulls
    }


async def fetch_ga4_total(
    client: GoogleSeam, *, property_id: str, window_start: date_cls, window_end: date_cls
) -> dict[str, Any]:
    """Fetch the date-only (total) runReport — the A11 source of truth for totals."""
    url = f"{GA4_BASE}/properties/{property_id}:runReport"
    return await client.post(url, _body(_TOTAL_METRICS, [_date_dim()], window_start, window_end))


async def fetch_ga4_channels(
    client: GoogleSeam, *, property_id: str, window_start: date_cls, window_end: date_cls
) -> dict[str, Any]:
    """Fetch the date × channel runReport (traffic-source breakdown)."""
    url = f"{GA4_BASE}/properties/{property_id}:runReport"
    dims = [_date_dim(), {"name": "sessionDefaultChannelGroup"}]
    return await client.post(url, _body(_CHANNEL_METRICS, dims, window_start, window_end))


def _is_sampled(payload: dict[str, Any]) -> bool:
    """Any non-empty ``samplingMetadatas`` on the report means it was sampled (A11)."""
    metas = payload.get("metadata", {}).get("samplingMetadatas")
    return bool(metas)


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
                # GA4 renamed "conversions" → "keyEvents"; carry it in both columns
                # so reads.analytics (which sums `conversions`) isn't permanently 0.
                conversions=_dec(mets, mi.get("keyEvents")),
                avg_session_duration=_dec(mets, mi.get("averageSessionDuration")),
                is_sampled=sampled,
            )
        )

    return rows


def _ga4_date(raw: str) -> str:
    """GA4 ``date`` dimension is ``YYYYMMDD`` — expand to ISO ``YYYY-MM-DD``."""
    if len(raw) == 8 and raw.isdigit():
        return f"{raw[0:4]}-{raw[4:6]}-{raw[6:8]}"
    return raw
