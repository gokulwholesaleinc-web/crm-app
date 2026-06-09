"""Google Ads ingest — campaign + ad-group GAQL fetchers + pure mapper.

REST against ``customers/{cid}/googleAds:searchStream`` (GAQL) — NO ``google-ads``
gRPC dep (C1). TWO GAQL grains are pulled and merged into one landing dict:

* **FROM campaign** — account + campaign grain. CRITICAL (C1): this is the ONLY
  grain that includes Performance Max / Smart / Demand Gen / App campaigns, which
  have NO ``ad_group`` resources. Account-level "Total Spend" is summed from THESE
  campaign rows, so PMax spend/conversions are no longer silently dropped. (The
  prior bug synthesized account+campaign totals from ``FROM ad_group``, which omits
  every ad-group-less campaign → headline spend undercounted with no error.)
* **FROM ad_group** — ad-group grain only. Skipped on conversion-settling runs
  (``include_adgroups=False``, A7) so settling re-fetches just the campaign/account
  conversion window without re-pulling the heavier ad-group grain.

``map_google_ads`` is PURE over the merged payload. Money is reported as **micros**
→ ``money.from_micros`` (÷1e6) before any row (A4). ``conversions``/value are
fractional ``Decimal`` (A4). Each ``entity_level`` is emitted exactly once (A2).
Empty result → ``[]`` (E5); a drifted envelope raises ``UnmappableShapeError`` so
the run is recorded ``partial`` rather than a silent zero (CRITICAL-1).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date as date_cls
from decimal import Decimal
from typing import Any

from ..money import from_micros, q6
from ..rows import AdGroupDimRow, AdsDailyRow, CampaignDimRow
from .http_client import GOOGLE_ADS_BASE, GoogleSeam, UnmappableShapeError, ensure_shape

# Normalize the platform's verbatim status into the dim's canonical token.
_STATUS_MAP = {"ENABLED": "enabled", "PAUSED": "paused", "REMOVED": "removed"}

# Campaign grain (PMax/Smart/Demand-Gen-inclusive). Account totals are summed from
# this, so ad-group-less campaigns are counted (C1).
GAQL_CAMPAIGN = (
    "SELECT segments.date, campaign.id, campaign.name, campaign.status, "
    "metrics.cost_micros, metrics.impressions, metrics.clicks, "
    "metrics.conversions, metrics.conversions_value "
    "FROM campaign "
    "WHERE segments.date BETWEEN '{start}' AND '{end}'"
)

# Ad-group grain. campaign.id links the ad-group to its campaign dim; the campaign
# name/status come from the campaign query, not here.
GAQL_ADGROUP = (
    "SELECT segments.date, campaign.id, "
    "ad_group.id, ad_group.name, ad_group.status, "
    "metrics.cost_micros, metrics.impressions, metrics.clicks, "
    "metrics.conversions, metrics.conversions_value "
    "FROM ad_group "
    "WHERE segments.date BETWEEN '{start}' AND '{end}'"
)


async def _search(
    client: GoogleSeam, *, customer_id: str, developer_token: str,
    login_customer_id: str | None, gaql: str,
) -> list[dict[str, Any]]:
    """One searchStream POST → the list of batch objects (each ``{"results": [...]}``)."""
    url = f"{GOOGLE_ADS_BASE}/customers/{customer_id}/googleAds:searchStream"
    headers = {"developer-token": developer_token}
    if login_customer_id:
        headers["login-customer-id"] = login_customer_id
    body = await client.post(url, {"query": gaql}, headers=headers)
    # searchStream returns a top-level array of batch objects; the seam may hand back
    # a bare list, a single non-streamed {"results": [...]}, or {"batches": [...]}.
    if isinstance(body, list):
        return body
    if "results" in body:
        return [body]
    return body.get("batches", [])


async def fetch_google_ads(
    client: GoogleSeam,
    *,
    customer_id: str,
    developer_token: str,
    login_customer_id: str | None,
    window_start: date_cls,
    window_end: date_cls,
    include_adgroups: bool = True,
) -> dict[str, Any]:
    """Fetch the campaign grain (+ optionally the ad-group grain) for a window.

    Returns a merged landing dict ``{"campaign_batches": [...], "adgroup_batches":
    [...]}`` (account-currency micros). ``include_adgroups=False`` (settling, A7)
    pulls only the campaign grain so the conversion re-fetch doesn't re-run the
    heavier ad-group query.
    """
    campaign_batches = await _search(
        client, customer_id=customer_id, developer_token=developer_token,
        login_customer_id=login_customer_id,
        gaql=GAQL_CAMPAIGN.format(start=window_start.isoformat(), end=window_end.isoformat()),
    )
    adgroup_batches: list[dict[str, Any]] = []
    if include_adgroups:
        adgroup_batches = await _search(
            client, customer_id=customer_id, developer_token=developer_token,
            login_customer_id=login_customer_id,
            gaql=GAQL_ADGROUP.format(start=window_start.isoformat(), end=window_end.isoformat()),
        )
    return {"campaign_batches": campaign_batches, "adgroup_batches": adgroup_batches}


def _norm_status(raw: str | None) -> tuple[str | None, str | None]:
    if not raw:
        return None, None
    return _STATUS_MAP.get(raw.upper(), raw.lower()), raw


def _iter_results(batches: list[dict[str, Any]] | None):
    for batch in batches or []:
        yield from batch.get("results", []) or []


def _measures(result: dict[str, Any]) -> tuple[Decimal, int, int, Decimal, Decimal]:
    m = result.get("metrics", {})
    return (
        from_micros(m.get("costMicros", 0)),
        int(m.get("impressions", 0) or 0),
        int(m.get("clicks", 0) or 0),
        q6(m.get("conversions", 0) or 0),
        q6(m.get("conversionsValue", 0) or 0),
    )


def _row_date(result: dict[str, Any]) -> date_cls:
    seg = result.get("segments", {})
    ensure_shape(
        isinstance(seg, dict) and bool(seg.get("date")),
        "google_ads result row missing segments.date",
        platform="google_ads",
    )
    return date_cls.fromisoformat(seg["date"])


def map_google_ads(
    payload: dict[str, Any],
    *,
    connection_id: int,
    company_id: int,
    currency: str | None = None,
) -> tuple[list[AdsDailyRow], list[CampaignDimRow], list[AdGroupDimRow]]:
    """Pure: merged campaign+ad-group payload → (ads rows, campaign dims, ad-group dims).

    Campaign-level facts come directly from the FROM-campaign grain (PMax-inclusive,
    C1); account-level facts are summed from those campaign rows; ad-group-level
    facts come from the FROM-ad_group grain (absent on settling runs). Each level is
    a distinct ``entity_level`` so every read filters to exactly one (A2). Money via
    ``from_micros`` (A4). Empty payload → empty lists (E5); a missing
    ``campaign_batches`` envelope raises (CRITICAL-1).
    """
    # Envelope guard (CRITICAL-1): the fetcher always lands {"campaign_batches": [...]}.
    ensure_shape(
        isinstance(payload, dict) and isinstance(payload.get("campaign_batches"), list),
        "google_ads payload missing 'campaign_batches' list envelope",
        platform="google_ads",
    )

    ads: list[AdsDailyRow] = []
    campaigns: dict[str, CampaignDimRow] = {}
    adgroups: dict[str, AdGroupDimRow] = {}

    def _accum() -> dict[str, Any]:
        return {"spend": Decimal("0"), "impr": 0, "clicks": 0, "conv": Decimal("0"), "val": Decimal("0")}

    acct: dict[date_cls, dict[str, Any]] = defaultdict(_accum)

    # ── campaign grain → campaign facts + campaign dims + account roll-up ──
    for result in _iter_results(payload["campaign_batches"]):
        row_date = _row_date(result)
        campaign = result.get("campaign", {})
        campaign_id = str(campaign.get("id")) if campaign.get("id") is not None else None
        if campaign_id is None:
            raise UnmappableShapeError(
                "google_ads campaign row missing campaign.id", platform="google_ads"
            )
        spend, impressions, clicks, conversions, conversion_value = _measures(result)

        ads.append(
            AdsDailyRow(
                connection_id=connection_id, company_id=company_id, platform="google_ads",
                date=row_date, entity_level="campaign", campaign_id=campaign_id, adgroup_id=None,
                spend=spend, impressions=impressions, clicks=clicks,
                conversions=conversions, conversion_value=conversion_value, currency=currency,
            )
        )
        if campaign_id not in campaigns:
            status, raw_status = _norm_status(campaign.get("status"))
            campaigns[campaign_id] = CampaignDimRow(
                connection_id=connection_id, campaign_id=campaign_id,
                name=campaign.get("name"), status=status, raw_status=raw_status,
            )
        b = acct[row_date]
        b["spend"] += spend
        b["impr"] += impressions
        b["clicks"] += clicks
        b["conv"] += conversions
        b["val"] += conversion_value

    # account-level roll-up (NULL campaign/adgroup grain, A2) — summed from the
    # campaign grain so PMax/Smart/Demand-Gen are included (C1).
    for row_date, b in acct.items():
        ads.append(
            AdsDailyRow(
                connection_id=connection_id, company_id=company_id, platform="google_ads",
                date=row_date, entity_level="account", campaign_id=None, adgroup_id=None,
                spend=q6(b["spend"]), impressions=b["impr"], clicks=b["clicks"],
                conversions=q6(b["conv"]), conversion_value=q6(b["val"]), currency=currency,
            )
        )

    # ── ad-group grain → ad-group facts + ad-group dims (skipped on settling) ──
    for result in _iter_results(payload.get("adgroup_batches")):
        row_date = _row_date(result)
        campaign = result.get("campaign", {})
        ad_group = result.get("adGroup", {})
        campaign_id = str(campaign.get("id")) if campaign.get("id") is not None else None
        adgroup_id = str(ad_group.get("id")) if ad_group.get("id") is not None else None
        if adgroup_id is None:
            raise UnmappableShapeError(
                "google_ads ad-group row missing ad_group.id", platform="google_ads"
            )
        spend, impressions, clicks, conversions, conversion_value = _measures(result)

        ads.append(
            AdsDailyRow(
                connection_id=connection_id, company_id=company_id, platform="google_ads",
                date=row_date, entity_level="adgroup", campaign_id=campaign_id, adgroup_id=adgroup_id,
                spend=spend, impressions=impressions, clicks=clicks,
                conversions=conversions, conversion_value=conversion_value, currency=currency,
            )
        )
        if adgroup_id not in adgroups:
            ag_status, _ = _norm_status(ad_group.get("status"))
            adgroups[adgroup_id] = AdGroupDimRow(
                connection_id=connection_id, adgroup_id=adgroup_id, campaign_id=campaign_id,
                name=ad_group.get("name"), status=ag_status,
            )

    return ads, list(campaigns.values()), list(adgroups.values())
