"""Meta Ads ingest — async-insights fetcher + pure mapper (Phase 2, dark).

The Meta Marketing API insights edge for non-trivial windows uses an ASYNC report
flow, NOT a synchronous GET:

  1. POST ``/act_<id>/insights`` (level=adset, time_increment=1) → ``report_run_id``;
  2. poll ``GET /<report_run_id>`` until ``async_status == "Job Completed"``
     (``Job Failed``/``Job Skipped`` → permanent error);
  3. page ``GET /<report_run_id>/insights`` (cursor paging);
  4. fetch the campaign + ad-set dims (``/act_<id>/campaigns``, ``/act_<id>/adsets``)
     for names + statuses.

Everything is merged into one landing dict ``{"insights", "campaigns", "adsets"}``
that ``map_meta_ads`` consumes as a PURE function. Correctness:

* Money is account-currency decimal STRINGS → ``money.to_money`` (NOT micros, A4).
* ``conversions``/``conversion_value`` come from the ``actions``/``action_values``
  PURCHASE entry (single highest-priority type — never summed across purchase
  variants, which would double-count).
* Ad-set grain rolls up to campaign + account (additive measures). ``reach`` is
  NON-additive (dedup), so it is kept only at the ad-set grain and left ``None`` on
  the campaign/account roll-ups. (Unlike Google PMax, Meta campaigns always have an
  ad set, so the ad-set roll-up captures all spend — no ad-group-less gap.)
* The 7d_view/28d_view attribution windows were removed Jan 2026 and return EMPTY,
  so we use the account's unified attribution setting; an empty result → ``[]``
  (E5). A drifted envelope raises ``UnmappableShapeError`` → ``partial`` (CRITICAL-1).
"""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from datetime import date as date_cls
from decimal import Decimal
from typing import Any

from ..money import q6, to_money
from ..rows import AdGroupDimRow, AdsDailyRow, CampaignDimRow
from .http_client import (
    META_GRAPH_BASE,
    MetaSeam,
    PermanentError,
    TransientError,
    UnmappableShapeError,
    ensure_shape,
)

_PAGE_LIMIT = 500  # Meta insights/list page size
_MAX_PAGES = 50  # bound cursor paging so a runaway account can't blow the quota
_DEFAULT_POLL_INTERVAL = 2.0  # seconds between async-status polls
_DEFAULT_MAX_POLLS = 30  # ~60s ceiling; daily/settling windows complete fast

# Insight fields requested at the ad-set grain (one row per adset per day).
_INSIGHT_FIELDS = (
    "campaign_id,campaign_name,adset_id,adset_name,"
    "spend,impressions,clicks,reach,actions,action_values"
)

# Meta effective_status → the dim's canonical token (reads.campaigns counts
# 'active'/'enabled' as live; ACTIVE lowercases to active and is counted).
_STATUS_MAP = {
    "ACTIVE": "active",
    "PAUSED": "paused",
    "CAMPAIGN_PAUSED": "paused",
    "ADSET_PAUSED": "paused",
    "ARCHIVED": "removed",
    "DELETED": "removed",
}

# Priority order for the purchase conversion — pick the FIRST present type, never
# sum (omni_purchase already dedups pixel/app/offline; summing would double-count).
_PURCHASE_PRIORITY = ("omni_purchase", "purchase", "offsite_conversion.fb_pixel_purchase")


# ── fetch (the async report flow) ─────────────────────────────────────────────
def _submit_params(window_start: date_cls, window_end: date_cls) -> dict[str, Any]:
    return {
        "level": "adset",
        "fields": _INSIGHT_FIELDS,
        "time_range": json.dumps({"since": window_start.isoformat(), "until": window_end.isoformat()}),
        "time_increment": 1,
        # Use the account's configured attribution windows — dodges the removed
        # 7d_view/28d_view trap (those now return EMPTY datasets, not errors).
        "use_unified_attribution_setting": "true",
        "limit": _PAGE_LIMIT,
    }


async def _await_report(
    client: MetaSeam, report_run_id: str, *, poll_interval: float, max_polls: int
) -> None:
    """Poll the async report until it completes (or fails/times out)."""
    url = f"{META_GRAPH_BASE}/{report_run_id}"
    for _ in range(max_polls):
        status = await client.get(url, {"fields": "async_status,async_percent_completion"})
        state = (status or {}).get("async_status")
        if state == "Job Completed":
            return
        if state in ("Job Failed", "Job Skipped"):
            raise PermanentError(
                f"Meta async insights report {state}", error_class="meta_report_failed"
            )
        await asyncio.sleep(poll_interval)
    raise TransientError(
        "Meta async insights report did not complete in time", error_class="meta_report_timeout"
    )


async def _fetch_paged(
    client: MetaSeam, url: str, base_params: dict[str, Any], *, max_pages: int = _MAX_PAGES
) -> list[dict[str, Any]]:
    """Collect ``data`` across cursor pages (``paging.cursors.after``)."""
    out: list[dict[str, Any]] = []
    params = dict(base_params)
    for _ in range(max_pages):
        page = await client.get(url, params)
        # Drift guard at the fetch boundary (CRITICAL-1), checked on EVERY page: Meta
        # list/insights edges always return {"data": [...]} (empty list = genuine
        # no-data). A 2xx body without 'data' (incl. a mid-pagination drift) is raised
        # rather than normalized to [] and recorded as a silent zero. (OAuth-190 etc.
        # are 4xx → already PermanentError.)
        ensure_shape(
            isinstance(page, dict) and "data" in page,
            "meta_ads: unrecognized list/insights response envelope",
            platform="meta_ads",
        )
        out.extend(page.get("data") or [])
        paging = page.get("paging") or {}
        after = (paging.get("cursors") or {}).get("after")
        if not paging.get("next") or not after:
            break
        params = {**base_params, "after": after}
    return out


async def fetch_meta_ads(
    client: MetaSeam,
    *,
    account_id: str,
    window_start: date_cls,
    window_end: date_cls,
    poll_interval: float = _DEFAULT_POLL_INTERVAL,
    max_polls: int = _DEFAULT_MAX_POLLS,
) -> dict[str, Any]:
    """Run the async report + dim fetches; return the merged landing dict.

    ``account_id`` is the ``act_<id>`` form (A10-normalized on the connection).
    """
    submit = await client.post(
        f"{META_GRAPH_BASE}/{account_id}/insights", _submit_params(window_start, window_end)
    )
    report_run_id = (submit or {}).get("report_run_id")
    if not report_run_id:
        raise PermanentError(
            "Meta insights submit returned no report_run_id", error_class="meta_no_report_id"
        )
    await _await_report(client, str(report_run_id), poll_interval=poll_interval, max_polls=max_polls)

    insights = await _fetch_paged(
        client, f"{META_GRAPH_BASE}/{report_run_id}/insights", {"limit": _PAGE_LIMIT}
    )
    campaigns = await _fetch_paged(
        client,
        f"{META_GRAPH_BASE}/{account_id}/campaigns",
        {"fields": "id,name,effective_status", "limit": _PAGE_LIMIT},
    )
    adsets = await _fetch_paged(
        client,
        f"{META_GRAPH_BASE}/{account_id}/adsets",
        {"fields": "id,name,campaign_id,effective_status", "limit": _PAGE_LIMIT},
    )
    return {"insights": insights, "campaigns": campaigns, "adsets": adsets}


# ── pure mapper ───────────────────────────────────────────────────────────────
def _norm_status(raw: str | None) -> tuple[str | None, str | None]:
    if not raw:
        return None, None
    return _STATUS_MAP.get(raw.upper(), raw.lower()), raw


def _int(value: Any) -> int:
    if value in (None, ""):
        return 0
    return int(float(value))


def _purchase_value(entries: Any) -> Decimal:
    """The purchase value from an ``actions``/``action_values`` list — first present
    priority type, never summed across variants (avoids double-counting)."""
    if not entries:
        return Decimal("0")
    by_type = {e.get("action_type"): e.get("value") for e in entries if isinstance(e, dict)}
    for action_type in _PURCHASE_PRIORITY:
        value = by_type.get(action_type)
        if value not in (None, ""):
            return q6(value)
    return Decimal("0")


def map_meta_ads(
    payload: dict[str, Any],
    *,
    connection_id: int,
    company_id: int,
    currency: str | None = None,
) -> tuple[list[AdsDailyRow], list[CampaignDimRow], list[AdGroupDimRow]]:
    """Pure: merged Meta landing dict → (ads rows, campaign dims, ad-group dims).

    Ad-set facts (entity_level='adgroup') roll up to campaign + account (additive;
    reach excluded from roll-ups). Money via ``to_money`` (NOT micros). Empty
    insights → empty ads (E5); a missing ``insights`` envelope raises (CRITICAL-1).
    """
    ensure_shape(
        isinstance(payload, dict) and isinstance(payload.get("insights"), list),
        "meta_ads payload missing 'insights' list envelope",
        platform="meta_ads",
    )

    ads: list[AdsDailyRow] = []

    def _accum() -> dict[str, Any]:
        return {"spend": Decimal("0"), "impr": 0, "clicks": 0, "conv": Decimal("0"),
                "val": Decimal("0"), "purch": Decimal("0")}

    acct: dict[date_cls, dict[str, Any]] = defaultdict(_accum)
    camp: dict[tuple[str, date_cls], dict[str, Any]] = defaultdict(_accum)

    for row in payload["insights"]:
        date_str = row.get("date_start")
        ensure_shape(
            bool(date_str), "meta_ads insight row missing date_start", platform="meta_ads"
        )
        row_date = date_cls.fromisoformat(date_str)
        campaign_id = str(row["campaign_id"]) if row.get("campaign_id") else None
        adset_id = str(row["adset_id"]) if row.get("adset_id") else None
        if adset_id is None:
            raise UnmappableShapeError(
                "meta_ads insight row missing adset_id (level=adset grain)", platform="meta_ads"
            )

        spend = to_money(row.get("spend", 0))
        impressions = _int(row.get("impressions"))
        clicks = _int(row.get("clicks"))
        reach = _int(row.get("reach")) if row.get("reach") not in (None, "") else None
        purchases = _purchase_value(row.get("actions"))
        conversion_value = _purchase_value(row.get("action_values"))
        conversions = purchases  # Meta's primary conversion for this dashboard

        ads.append(
            AdsDailyRow(
                connection_id=connection_id, company_id=company_id, platform="meta_ads",
                date=row_date, entity_level="adgroup", campaign_id=campaign_id, adgroup_id=adset_id,
                spend=spend, impressions=impressions, clicks=clicks,
                conversions=conversions, conversion_value=conversion_value,
                reach=reach, purchases=purchases, currency=currency,
            )
        )

        targets = [acct[row_date]]
        if campaign_id:
            targets.append(camp[(campaign_id, row_date)])
        for bucket in targets:
            bucket["spend"] += spend
            bucket["impr"] += impressions
            bucket["clicks"] += clicks
            bucket["conv"] += conversions
            bucket["val"] += conversion_value
            bucket["purch"] += purchases

    # campaign-level roll-ups (NULL adgroup grain, A2; reach non-additive → None)
    for (c_id, row_date), b in camp.items():
        ads.append(
            AdsDailyRow(
                connection_id=connection_id, company_id=company_id, platform="meta_ads",
                date=row_date, entity_level="campaign", campaign_id=c_id, adgroup_id=None,
                spend=q6(b["spend"]), impressions=b["impr"], clicks=b["clicks"],
                conversions=q6(b["conv"]), conversion_value=q6(b["val"]),
                reach=None, purchases=q6(b["purch"]), currency=currency,
            )
        )

    # account-level roll-ups (NULL campaign/adgroup grain, A2; reach → None)
    for row_date, b in acct.items():
        ads.append(
            AdsDailyRow(
                connection_id=connection_id, company_id=company_id, platform="meta_ads",
                date=row_date, entity_level="account", campaign_id=None, adgroup_id=None,
                spend=q6(b["spend"]), impressions=b["impr"], clicks=b["clicks"],
                conversions=q6(b["conv"]), conversion_value=q6(b["val"]),
                reach=None, purchases=q6(b["purch"]), currency=currency,
            )
        )

    campaigns = _campaign_dims(payload.get("campaigns"), connection_id)
    adgroups = _adgroup_dims(payload.get("adsets"), connection_id)
    return ads, campaigns, adgroups


def _campaign_dims(rows: Any, connection_id: int) -> list[CampaignDimRow]:
    out: list[CampaignDimRow] = []
    for c in rows or []:
        cid = str(c["id"]) if c.get("id") else None
        if not cid:
            continue
        status, raw_status = _norm_status(c.get("effective_status") or c.get("status"))
        out.append(
            CampaignDimRow(
                connection_id=connection_id, campaign_id=cid,
                name=c.get("name"), status=status, raw_status=raw_status,
            )
        )
    return out


def _adgroup_dims(rows: Any, connection_id: int) -> list[AdGroupDimRow]:
    out: list[AdGroupDimRow] = []
    for a in rows or []:
        aid = str(a["id"]) if a.get("id") else None
        if not aid:
            continue
        status, _ = _norm_status(a.get("effective_status") or a.get("status"))
        out.append(
            AdGroupDimRow(
                connection_id=connection_id, adgroup_id=aid,
                campaign_id=str(a["campaign_id"]) if a.get("campaign_id") else None,
                name=a.get("name"), status=status,
            )
        )
    return out
