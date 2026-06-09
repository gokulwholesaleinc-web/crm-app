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


@dataclass(frozen=True, slots=True)
class AdsDailyRow:
    """One ``ads_daily_metrics`` grain (Meta or Google Ads)."""

    connection_id: int
    company_id: int
    platform: str
    date: date
    entity_level: str  # account | campaign | adgroup
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


@dataclass(frozen=True, slots=True)
class AnalyticsDailyRow:
    """One ``analytics_daily`` grain (GA4 or GSC)."""

    connection_id: int
    company_id: int
    source: str  # ga4 | gsc
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
