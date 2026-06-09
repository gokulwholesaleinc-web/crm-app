"""Typed upsert rows — the contract between ingest mappers and the warehouse.

Frozen dataclasses (not pydantic — internal, hot path) carrying exactly one
fact-table grain each. Mappers (``mapping.py``) produce these from captured API
payloads as *pure functions*; the warehouse (``warehouse.py``) consumes them.
Money + conversions are ``Decimal`` end-to-end (A4) — Google micros are already
normalized ÷1e6 by the mapper before a row is built (NN-8).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

EntityLevel = Literal["account", "campaign", "adgroup"]
AnalyticsSource = Literal["ga4", "gsc"]


@dataclass(frozen=True, slots=True)
class AdsDailyRow:
    """One ``ads_daily_metrics`` grain (Meta or Google Ads).

    The grain↔id correlation is a load-bearing A2 invariant (it's what keeps
    account/campaign/adgroup rollups from double-counting). ``__post_init__``
    enforces it at construction — an account row carrying a campaign_id, or a
    campaign row with no campaign_id, fails loudly at the mapper instead of
    silently mis-graining a fact and surviving to a wrong dashboard number.
    """

    connection_id: int
    company_id: int
    platform: str
    date: date
    entity_level: EntityLevel
    spend: Decimal
    impressions: int
    clicks: int
    conversions: Decimal
    conversion_value: Decimal
    campaign_id: str | None = None
    adgroup_id: str | None = None
    reach: int | None = None
    purchases: Decimal | None = None
    currency: str | None = None

    def __post_init__(self) -> None:
        level, camp, ag = self.entity_level, self.campaign_id, self.adgroup_id
        if level == "account" and (camp is not None or ag is not None):
            raise ValueError("account-level row must have NULL campaign_id and adgroup_id")
        if level == "campaign" and (camp is None or ag is not None):
            raise ValueError("campaign-level row must have campaign_id and NULL adgroup_id")
        if level == "adgroup" and ag is None:
            raise ValueError("adgroup-level row must have an adgroup_id")


@dataclass(frozen=True, slots=True)
class AnalyticsDailyRow:
    """One ``analytics_daily`` grain (GA4 or GSC)."""

    connection_id: int
    company_id: int
    source: AnalyticsSource  # ga4 | gsc
    date: date
    dimension_type: str  # total | channel | page | query | source_medium
    dimension_value: str = ""
    sessions: int | None = None
    users: int | None = None
    new_users: int | None = None
    engaged_sessions: int | None = None
    engagement_rate: Decimal | None = None
    bounce_rate: Decimal | None = None
    conversions: Decimal | None = None
    key_events: Decimal | None = None
    avg_session_duration: Decimal | None = None
    impressions: int | None = None
    clicks: int | None = None
    ctr: Decimal | None = None
    position: Decimal | None = None
    is_sampled: bool = False
    # GA4 truthfulness (A11 / H3): False when the report had a high-cardinality
    # "(other)" overflow (metadata.dataLossFromOtherRow) or was not yet finalized
    # (metadata.dataGolden=False) — so the read layer can disclose that a breakdown
    # may not tie out to the totals.
    is_data_golden: bool = True


@dataclass(frozen=True, slots=True)
class SiteHealthRow:
    """One ``site_health_snapshots`` grain (PageSpeed)."""

    connection_id: int
    company_id: int
    captured_date: date
    strategy: str  # mobile | desktop
    url: str
    performance_score: Decimal | None = None
    seo_score: Decimal | None = None
    accessibility_score: Decimal | None = None
    best_practices_score: Decimal | None = None
    lcp_ms: int | None = None
    cls: Decimal | None = None
    inp_ms: int | None = None


@dataclass(frozen=True, slots=True)
class SocialDailyRow:
    """One ``social_daily_metrics`` grain (organic IG/FB/…) — generic long-format.

    ``value`` is the raw measure (follower count / reach / impressions / views /
    engagement) as ``Decimal`` — never a derived ratio. One row per
    ``(connection, date, platform, metric_key)``.
    """

    connection_id: int
    company_id: int
    platform: str
    date: date
    metric_key: str
    value: Decimal


@dataclass(frozen=True, slots=True)
class CampaignDimRow:
    """One ``marketing_campaigns`` dimension row (A3): name + current status.

    Facts carry campaign_id only; "Active Campaigns" and labels read this dim.
    ``status`` is the normalized form (``enabled``/``paused``/``removed``);
    ``raw_status`` preserves the platform's verbatim string for audit.
    """

    connection_id: int
    campaign_id: str
    name: str | None = None
    status: str | None = None
    raw_status: str | None = None


@dataclass(frozen=True, slots=True)
class AdGroupDimRow:
    """One ``marketing_ad_groups`` dimension row (A3)."""

    connection_id: int
    adgroup_id: str
    campaign_id: str | None = None
    name: str | None = None
    status: str | None = None
