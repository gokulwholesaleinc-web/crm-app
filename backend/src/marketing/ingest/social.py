"""Organic-social ingest (Phase 4) — Graph API insights + pure mapper.

Instagram + Facebook organic metrics share ONE thin REST path against the Meta
Graph ``/{object_id}/insights`` endpoint and ONE pure mapper over the standard
insights envelope (``{"data": [{"name", "period", "values": [{"value", "end_time"}]}]}``),
landing generic ``social_daily_metrics`` rows ``(platform, date, metric_key, value)``.
Reuses the Meta Graph client/seam (token + ``appsecret_proof``) — IG/FB organic is
the same API surface as Meta Ads, so no new network client (DRY).

TikTok/LinkedIn are enum-valid but unwired (App-Review-gated human work); no
handler exists for them, so they can't sync.

The exact metric names + day-boundary attribution are deploy-time tie-out details
(Graph version + App Review gate); this whole feature ships dark behind
``MKTG_SOCIAL_ENABLED``. The mapper is generic over whatever metric names the API
returns, so a metric rename doesn't break the shape — only a renamed/absent
``data`` envelope does (→ ``UnmappableShapeError`` → ``partial``, CRITICAL-1).
"""

from __future__ import annotations

from datetime import date as date_cls
from datetime import timedelta
from typing import Any, cast

from ..money import q6
from ..rows import SocialDailyRow
from .http_client import META_GRAPH_BASE, MetaSeam, ensure_shape

# Per-platform day-metric sets (verify availability at enable time — Graph version +
# App Review can gate/rename these; the mapper tolerates whatever comes back).
IG_METRICS = ("reach", "profile_views", "follower_count")
FB_METRICS = ("page_impressions_unique", "page_post_engagements", "page_fans", "page_views_total")


async def fetch_social_insights(
    client: MetaSeam,
    *,
    object_id: str,
    metrics: tuple[str, ...],
    window_start: date_cls,
    window_end: date_cls,
    platform: str,
    period: str = "day",
) -> dict[str, Any]:
    """Fetch day-grain insights for one social object (IG user / FB page).

    ``until`` is exclusive on the Graph API, so it is pushed one day past
    ``window_end`` to include it. Drift guard at the fetch boundary (CRITICAL-1):
    a genuine no-data response still carries a ``data`` list; an ``error`` body or
    a renamed envelope raises rather than normalizing to a silent zero.
    """
    url = f"{META_GRAPH_BASE}/{object_id}/insights"
    params = {
        "metric": ",".join(metrics),
        "period": period,
        "since": window_start.isoformat(),
        "until": (window_end + timedelta(days=1)).isoformat(),
    }
    payload = await client.get(url, params)
    ensure_shape(
        isinstance(payload, dict) and "error" not in payload and isinstance(payload.get("data"), list),
        "social insights: unrecognized response envelope",
        platform=platform,
    )
    return payload


def _insights_date(end_time: str) -> date_cls:
    """The day a Graph insights value belongs to. ``end_time`` is ISO-8601
    (``2026-06-01T07:00:00+0000``); we key on its date part. (Exact day-boundary
    attribution vs the account TZ is a deploy-time tie-out detail, A8.)"""
    return date_cls.fromisoformat(end_time[:10])


def map_social_insights(
    payload: dict[str, Any],
    *,
    connection_id: int,
    company_id: int,
    platform: str,
) -> list[SocialDailyRow]:
    """Pure: a Graph insights payload → per-(date, metric) ``SocialDailyRow``s.

    Iterates ``data[].values[]`` (the day time-series). Breakdown-shaped values
    (a dict instead of a scalar) are skipped — this fact stores scalar daily
    metrics only. Empty data / missing end_time → no row (E5). A payload missing
    the ``data`` envelope, or a metric missing its ``name``, is drift → raise.
    """
    ensure_shape(
        isinstance(payload, dict) and isinstance(payload.get("data"), list),
        "social insights payload missing 'data' list envelope",
        platform=platform,
    )

    rows: list[SocialDailyRow] = []
    for metric in payload["data"]:
        name = metric.get("name") if isinstance(metric, dict) else None
        ensure_shape(bool(name), "social insights metric missing 'name'", platform=platform)
        # CRITICAL-1: a renamed/absent 'values' key (a Graph version rename like
        # values→value) is DRIFT, not a no-data metric — raise rather than silently
        # emit zero rows and land a green 'success' on data that was never ingested.
        # A genuinely empty list is legitimate no-data (E5 → no row).
        values = metric.get("values")
        ensure_shape(
            isinstance(values, list),
            f"social insights metric '{name}' missing 'values' list",
            platform=platform,
        )
        # `or []` is dead after the ensure_shape above (values is a list) — it only
        # narrows the static type off `Any | None` for the checker.
        for v in values or []:
            if not isinstance(v, dict):
                continue
            value = v.get("value")
            # Breakdown-shaped values (a dict) → skip; this fact stores scalars only.
            if isinstance(value, dict):
                continue
            # The date grain depends on end_time — a scalar point missing it is drift
            # (a renamed end_time→endTime), not empty data → raise (symmetric with the
            # GSC/GA4 inner-field guards), never a silently-dropped point.
            end_time = v.get("end_time")
            ensure_shape(
                bool(end_time),
                "social insights value missing 'end_time'",
                platform=platform,
            )
            rows.append(
                SocialDailyRow(
                    connection_id=connection_id,
                    company_id=company_id,
                    platform=platform,
                    date=_insights_date(cast("str", end_time)),
                    metric_key=str(name)[:64],
                    value=q6(value or 0),
                )
            )
    return rows
