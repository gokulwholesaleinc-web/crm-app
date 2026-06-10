"""Google Ads ingest — searchStream fetcher + pure mapper.

REST against ``customers/{cid}/googleAds:searchStream`` (GAQL) — NO ``google-ads``
gRPC dep (C1). The fetcher returns the raw stream payload; ``map_google_ads`` is a
PURE function over that payload (no I/O) producing typed warehouse rows.

Correctness (A4 / A3 / A2):
* Money is reported as **micros** → ``money.from_micros`` (÷ 1e6) before any row
  is built. Meta is NOT micros — this is the Google-only normalization.
* ``conversions`` / ``conversions_value`` are fractional → ``Decimal`` (A4).
* Emits one account-level ``AdsDailyRow`` per date (summed across campaigns) AND
  one campaign-level row per (campaign, date), plus ``CampaignDimRow`` /
  ``AdGroupDimRow`` for the star dims (A3). Ad-group-level facts are emitted when
  the GAQL selects ad_group.
* Empty result (no rows) → ``[]`` (E5 empty-result guard — never raise).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date as date_cls
from decimal import Decimal
from typing import Any

from ..money import from_micros, q6
from ..rows import AdGroupDimRow, AdsDailyRow, CampaignDimRow
from .http_client import GOOGLE_ADS_BASE, GoogleSeam

# Normalize the platform's verbatim status into the dim's canonical token.
_STATUS_MAP = {"ENABLED": "enabled", "PAUSED": "paused", "REMOVED": "removed"}

# One GAQL pull at campaign+date grain with ad_group detail. segments.date gives
# the per-day bucket the warehouse keys on; conversions/value are fractional.
GAQL = (
    "SELECT segments.date, campaign.id, campaign.name, campaign.status, "
    "ad_group.id, ad_group.name, ad_group.status, "
    "metrics.cost_micros, metrics.impressions, metrics.clicks, "
    "metrics.conversions, metrics.conversions_value "
    "FROM ad_group "
    "WHERE segments.date BETWEEN '{start}' AND '{end}'"
)


async def fetch_google_ads(
    client: GoogleSeam,
    *,
    customer_id: str,
    developer_token: str,
    login_customer_id: str | None,
    window_start: date_cls,
    window_end: date_cls,
) -> dict[str, Any]:
    """Fetch the raw searchStream payload for a window (account-currency micros).

    ``customer_id`` is the bare 10-digit id (A10 normalized on the connection).
    Returns the decoded JSON: searchStream yields a JSON array of batches, each
    ``{"results": [...]}`` — we wrap it as ``{"batches": [...]}`` for a stable
    landing shape the mapper consumes.
    """
    url = f"{GOOGLE_ADS_BASE}/customers/{customer_id}/googleAds:searchStream"
    headers = {"developer-token": developer_token}
    if login_customer_id:
        headers["login-customer-id"] = login_customer_id
    query = GAQL.format(start=window_start.isoformat(), end=window_end.isoformat())
    body = await client.post(url, {"query": query}, headers=headers)
    # searchStream returns a top-level array of batch objects; request_with_retry
    # always hands back a dict, so a bare list arrives wrapped — normalize either.
    if isinstance(body, list):
        return {"batches": body}
    if "results" in body:  # a single non-streamed batch
        return {"batches": [body]}
    return {"batches": body.get("batches", [])}


def _norm_status(raw: str | None) -> tuple[str | None, str | None]:
    if not raw:
        return None, None
    return _STATUS_MAP.get(raw.upper(), raw.lower()), raw


def _iter_results(payload: dict[str, Any]):
    for batch in payload.get("batches", []) or []:
        yield from batch.get("results", []) or []


def map_google_ads(
    payload: dict[str, Any],
    *,
    connection_id: int,
    company_id: int,
    currency: str | None = None,
) -> tuple[list[AdsDailyRow], list[CampaignDimRow], list[AdGroupDimRow]]:
    """Pure: searchStream payload → (ads rows, campaign dims, ad-group dims).

    The GAQL grain is ad-group; from it we also roll up **campaign-level** and
    **account-level** facts by summing per date. Each level is a distinct
    ``entity_level`` so every read filters to exactly one (A2) — ``reads.campaigns``
    reads the campaign grain, ``reads.adgroups`` the ad-group grain, the overview
    the account grain — and none double-counts. Money normalized via
    ``from_micros`` (A4); empty payload → empty lists.
    """
    ads: list[AdsDailyRow] = []
    campaigns: dict[str, CampaignDimRow] = {}
    adgroups: dict[str, AdGroupDimRow] = {}

    def _accum() -> dict[str, Any]:
        return {"spend": Decimal("0"), "impr": 0, "clicks": 0, "conv": Decimal("0"), "val": Decimal("0")}

    # roll-up accumulators: account keyed by date, campaign keyed by (campaign_id, date)
    acct: dict[date_cls, dict[str, Any]] = defaultdict(_accum)
    camp: dict[tuple[str, date_cls], dict[str, Any]] = defaultdict(_accum)

    for result in _iter_results(payload):
        seg = result.get("segments", {})
        row_date = date_cls.fromisoformat(seg["date"])
        campaign = result.get("campaign", {})
        ad_group = result.get("adGroup", {})
        metrics = result.get("metrics", {})

        campaign_id = str(campaign.get("id")) if campaign.get("id") is not None else None
        adgroup_id = str(ad_group.get("id")) if ad_group.get("id") is not None else None

        spend = from_micros(metrics.get("costMicros", 0))
        impressions = int(metrics.get("impressions", 0) or 0)
        clicks = int(metrics.get("clicks", 0) or 0)
        conversions = q6(metrics.get("conversions", 0) or 0)
        conversion_value = q6(metrics.get("conversionsValue", 0) or 0)

        # ad-group-level fact (the GAQL grain)
        ads.append(
            AdsDailyRow(
                connection_id=connection_id,
                company_id=company_id,
                platform="google_ads",
                date=row_date,
                entity_level="adgroup",
                campaign_id=campaign_id,
                adgroup_id=adgroup_id,
                spend=spend,
                impressions=impressions,
                clicks=clicks,
                conversions=conversions,
                conversion_value=conversion_value,
                currency=currency,
            )
        )

        # dims (A3)
        if campaign_id and campaign_id not in campaigns:
            status, raw_status = _norm_status(campaign.get("status"))
            campaigns[campaign_id] = CampaignDimRow(
                connection_id=connection_id,
                campaign_id=campaign_id,
                name=campaign.get("name"),
                status=status,
                raw_status=raw_status,
            )
        if adgroup_id and adgroup_id not in adgroups:
            ag_status, _ = _norm_status(ad_group.get("status"))
            adgroups[adgroup_id] = AdGroupDimRow(
                connection_id=connection_id,
                adgroup_id=adgroup_id,
                campaign_id=campaign_id,
                name=ad_group.get("name"),
                status=ag_status,
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

    # campaign-level roll-up rows (NULL adgroup grain, A2) so reads.campaigns reads
    # a real campaign grain instead of re-summing ad-group facts.
    for (c_id, row_date), b in camp.items():
        ads.append(
            AdsDailyRow(
                connection_id=connection_id,
                company_id=company_id,
                platform="google_ads",
                date=row_date,
                entity_level="campaign",
                campaign_id=c_id,
                adgroup_id=None,
                spend=q6(b["spend"]),
                impressions=b["impr"],
                clicks=b["clicks"],
                conversions=q6(b["conv"]),
                conversion_value=q6(b["val"]),
                currency=currency,
            )
        )

    # account-level roll-up rows (NULL campaign/adgroup grain, A2)
    for row_date, b in acct.items():
        ads.append(
            AdsDailyRow(
                connection_id=connection_id,
                company_id=company_id,
                platform="google_ads",
                date=row_date,
                entity_level="account",
                campaign_id=None,
                adgroup_id=None,
                spend=q6(b["spend"]),
                impressions=b["impr"],
                clicks=b["clicks"],
                conversions=q6(b["conv"]),
                conversion_value=q6(b["val"]),
                currency=currency,
            )
        )

    return ads, list(campaigns.values()), list(adgroups.values())
