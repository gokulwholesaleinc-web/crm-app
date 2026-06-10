"""Pure mapper tests over committed fixtures — NO network, NO business-logic mock.

Each ``map_*`` is a pure function over a captured (anonymized) API payload, so the
whole correctness layer is provable offline. These assertions pin the locked
rules: A4 (Google micros ÷1e6, ``Decimal`` money/conversions), A11 (GA4 totals
only from the total query + ``is_sampled`` from ``samplingMetadatas``), A3
(campaign/ad-group dims with normalized status), A10/A2 (entity_level), and the E5
empty-result guard. No DB is needed — mappers don't touch a session.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from src.marketing.ingest import ga4, google_ads, gsc, pagespeed

FIXTURES = Path(__file__).resolve().parents[2] / "backend" / "src" / "marketing" / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


# ── Google Ads (A4 micros, A3 dims, A2 entity_level) ─────────────────────────
class TestGoogleAdsMapper:
    def test_emits_adgroup_campaign_and_account_rollups(self):
        ads, campaigns, adgroups = google_ads.map_google_ads(
            _load("google_ads_searchstream.json"), connection_id=7, company_id=3, currency="USD"
        )
        levels = {r.entity_level for r in ads}
        # ad-group (GAQL grain) + campaign roll-up + account roll-up — three distinct
        # entity_levels so reads.{adgroups,campaigns,overview} each filter to one (A2).
        assert levels == {"adgroup", "campaign", "account"}
        assert sum(r.entity_level == "adgroup" for r in ads) == 3
        account = [r for r in ads if r.entity_level == "account"]
        assert len(account) == 1
        # account row has NULL campaign/adgroup ids (A2 NULL grain)
        assert account[0].campaign_id is None and account[0].adgroup_id is None
        # campaign roll-ups carry campaign_id, NULL adgroup_id (A2), and re-sum to the
        # account total (every ad-group belongs to a campaign).
        camp_rows = [r for r in ads if r.entity_level == "campaign"]
        assert camp_rows and all(r.campaign_id and r.adgroup_id is None for r in camp_rows)
        assert sum((r.spend for r in camp_rows), Decimal("0")) == account[0].spend

    def test_micros_normalized_to_decimal_currency(self):
        ads, _, _ = google_ads.map_google_ads(
            _load("google_ads_searchstream.json"), connection_id=7, company_id=3, currency="USD"
        )
        account = next(r for r in ads if r.entity_level == "account")
        # 5,000,000 + 2,500,000 + 10,250,000 micros ÷ 1e6 = 17.75 (A4)
        assert account.spend == Decimal("17.75")
        assert isinstance(account.spend, Decimal)

    def test_conversions_are_fractional_decimal(self):
        ads, _, _ = google_ads.map_google_ads(
            _load("google_ads_searchstream.json"), connection_id=7, company_id=3
        )
        account = next(r for r in ads if r.entity_level == "account")
        # 3.5 + 1.0 + 6.25 = 10.75 — Integer would truncate to 10 (A4)
        assert account.conversions == Decimal("10.75")
        assert account.conversion_value == Decimal("515.75")  # 420.75 + 95.0 + 0.0

    def test_account_rollup_sums_volume(self):
        ads, _, _ = google_ads.map_google_ads(
            _load("google_ads_searchstream.json"), connection_id=7, company_id=3
        )
        account = next(r for r in ads if r.entity_level == "account")
        assert account.clicks == 80 + 20 + 210
        assert account.impressions == 1200 + 640 + 5400

    def test_campaign_dims_carry_normalized_status(self):
        _, campaigns, _ = google_ads.map_google_ads(
            _load("google_ads_searchstream.json"), connection_id=7, company_id=3
        )
        by_id = {c.campaign_id: c for c in campaigns}
        assert by_id["111"].status == "enabled" and by_id["111"].raw_status == "ENABLED"
        assert by_id["222"].status == "removed" and by_id["222"].raw_status == "REMOVED"
        assert by_id["111"].name == "Brand Search"

    def test_adgroup_dims_link_to_campaign(self):
        _, _, adgroups = google_ads.map_google_ads(
            _load("google_ads_searchstream.json"), connection_id=7, company_id=3
        )
        by_id = {a.adgroup_id: a for a in adgroups}
        assert by_id["911"].campaign_id == "111"
        assert by_id["912"].status == "paused"

    def test_empty_payload_guard(self):
        ads, campaigns, adgroups = google_ads.map_google_ads(
            {"batches": []}, connection_id=7, company_id=3
        )
        assert ads == [] and campaigns == [] and adgroups == []

    def test_streamed_list_shape_is_handled(self):
        # searchStream can hand back a bare list of batches; the mapper reads
        # ``batches`` only, so the fetcher's normalization is what wraps it.
        ads, _, _ = google_ads.map_google_ads({}, connection_id=7, company_id=3)
        assert ads == []


# ── GA4 (A11 total-vs-dimension, sampling) ───────────────────────────────────
class TestGa4Mapper:
    def test_total_query_produces_total_rows(self):
        rows = ga4.map_ga4(
            _load("ga4_runreport_total.json"), connection_id=5, company_id=9, dimension_type="total"
        )
        assert len(rows) == 2
        assert all(r.dimension_type == "total" for r in rows)
        assert all(r.dimension_value == "" for r in rows)
        first = next(r for r in rows if r.date == date(2026, 6, 1))
        assert first.sessions == 1320 and first.users == 1105 and first.new_users == 742
        assert first.engaged_sessions == 910
        assert first.engagement_rate == Decimal("0.689394")
        assert first.key_events == Decimal("37")
        # GA4 keyEvents IS the modern "conversions" — carried into the conversions
        # column too, so reads.analytics doesn't report a permanent 0 (M1).
        assert first.conversions == Decimal("37")
        assert first.source == "ga4"

    def test_total_query_is_not_sampled(self):
        rows = ga4.map_ga4(
            _load("ga4_runreport_total.json"), connection_id=5, company_id=9, dimension_type="total"
        )
        assert all(r.is_sampled is False for r in rows)

    def test_channel_query_sets_dimension_value(self):
        rows = ga4.map_ga4(
            _load("ga4_runreport_channels.json"), connection_id=5, company_id=9, dimension_type="channel"
        )
        assert {r.dimension_value for r in rows} == {"Organic Search", "Paid Search", "Direct"}
        assert all(r.dimension_type == "channel" for r in rows)

    def test_sampling_metadata_sets_is_sampled(self):
        # the channels fixture carries samplingMetadatas → every row flagged (A11)
        rows = ga4.map_ga4(
            _load("ga4_runreport_channels.json"), connection_id=5, company_id=9, dimension_type="channel"
        )
        assert rows and all(r.is_sampled is True for r in rows)

    def test_ga4_date_yyyymmdd_expanded(self):
        rows = ga4.map_ga4(
            _load("ga4_runreport_total.json"), connection_id=5, company_id=9, dimension_type="total"
        )
        assert {r.date for r in rows} == {date(2026, 6, 1), date(2026, 6, 2)}

    def test_empty_payload_guard(self):
        assert ga4.map_ga4({"rows": []}, connection_id=5, company_id=9, dimension_type="total") == []
        assert ga4.map_ga4({}, connection_id=5, company_id=9, dimension_type="total") == []


# ── GSC ──────────────────────────────────────────────────────────────────────
class TestGscMapper:
    def test_date_grain_metrics(self):
        rows = gsc.map_gsc(_load("gsc_searchanalytics.json"), connection_id=2, company_id=4)
        assert len(rows) == 2
        first = next(r for r in rows if r.date == date(2026, 6, 1))
        assert first.source == "gsc" and first.dimension_type == "total"
        assert first.clicks == 142 and first.impressions == 3890
        assert first.ctr == Decimal("0.0365")
        assert first.position == Decimal("8.42")

    def test_clicks_impressions_are_int(self):
        rows = gsc.map_gsc(_load("gsc_searchanalytics.json"), connection_id=2, company_id=4)
        assert all(isinstance(r.clicks, int) and isinstance(r.impressions, int) for r in rows)

    def test_empty_payload_guard(self):
        assert gsc.map_gsc({"rows": []}, connection_id=2, company_id=4) == []
        assert gsc.map_gsc({}, connection_id=2, company_id=4) == []


# ── PageSpeed ────────────────────────────────────────────────────────────────
class TestPageSpeedMapper:
    def test_scores_scaled_0_100(self):
        rows = pagespeed.map_pagespeed(
            _load("pagespeed_runpagespeed.json"), connection_id=8, company_id=1,
            captured_date=date(2026, 6, 2), strategy="mobile",
        )
        assert len(rows) == 1
        snap = rows[0]
        assert snap.performance_score == Decimal("74")  # 0.74 → 74
        assert snap.seo_score == Decimal("100")
        assert snap.accessibility_score == Decimal("92")
        assert snap.best_practices_score == Decimal("96")
        assert snap.strategy == "mobile"

    def test_core_web_vitals_from_audits(self):
        rows = pagespeed.map_pagespeed(
            _load("pagespeed_runpagespeed.json"), connection_id=8, company_id=1,
            captured_date=date(2026, 6, 2), strategy="desktop",
        )
        snap = rows[0]
        assert snap.lcp_ms == 2412
        assert snap.inp_ms == 186
        assert snap.cls == Decimal("0.041")
        assert snap.url == "https://www.example-client.com/"

    def test_missing_lighthouse_result_guard(self):
        assert pagespeed.map_pagespeed(
            {}, connection_id=8, company_id=1, captured_date=date(2026, 6, 2), strategy="mobile"
        ) == []

    def test_missing_category_yields_none(self):
        payload = {"lighthouseResult": {"finalUrl": "https://x.test/", "categories": {}, "audits": {}}}
        rows = pagespeed.map_pagespeed(
            payload, connection_id=8, company_id=1, captured_date=date(2026, 6, 2), strategy="mobile"
        )
        assert rows[0].performance_score is None
        assert rows[0].lcp_ms is None and rows[0].cls is None
