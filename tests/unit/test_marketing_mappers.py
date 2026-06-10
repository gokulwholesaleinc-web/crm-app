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

import pytest
from src.marketing import money
from src.marketing.ingest import ga4, google_ads, gsc, meta_ads, pagespeed
from src.marketing.ingest.http_client import UnmappableShapeError

FIXTURES = Path(__file__).resolve().parents[2] / "backend" / "src" / "marketing" / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


class TestMoneyGuards:
    def test_bool_is_rejected_not_coerced(self):
        # bool is an int subclass; a stray JSON true/false must NOT become $1.00/$0.00.
        for bad in (True, False):
            with pytest.raises(TypeError):
                money.to_money(bad)
            with pytest.raises(TypeError):
                money.from_micros(bad)

    def test_real_numbers_still_parse(self):
        assert money.to_money("5.00") == money.from_micros(5_000_000)


# ── Google Ads (A4 micros, A3 dims, A2 entity_level) ─────────────────────────
class TestGoogleAdsMapper:
    def test_emits_adgroup_campaign_and_account_levels(self):
        ads, campaigns, adgroups = google_ads.map_google_ads(
            _load("google_ads_searchstream.json"), connection_id=7, company_id=3, currency="USD"
        )
        levels = {r.entity_level for r in ads}
        # campaign grain (FROM campaign, PMax-inclusive) + account roll-up + ad-group
        # grain (FROM ad_group) — three distinct entity_levels so reads each filter to
        # exactly one (A2).
        assert levels == {"adgroup", "campaign", "account"}
        assert sum(r.entity_level == "campaign" for r in ads) == 3  # 111, 222, 333
        assert sum(r.entity_level == "adgroup" for r in ads) == 3  # 911, 912, 921
        account = [r for r in ads if r.entity_level == "account"]
        assert len(account) == 1
        assert account[0].campaign_id is None and account[0].adgroup_id is None  # A2 NULL grain
        camp_rows = [r for r in ads if r.entity_level == "campaign"]
        assert all(r.campaign_id and r.adgroup_id is None for r in camp_rows)
        # account is summed from the campaign grain (PMax-inclusive)
        assert sum((r.spend for r in camp_rows), Decimal("0")) == account[0].spend

    def test_c1_account_total_includes_pmax_campaign_without_adgroups(self):
        # C1: Performance Max campaign 333 has NO ad_group rows, yet its spend MUST be
        # in the account total — which is summed from the PMax-inclusive campaign grain.
        ads, campaigns, adgroups = google_ads.map_google_ads(
            _load("google_ads_searchstream.json"), connection_id=7, company_id=3, currency="USD"
        )
        account = next(r for r in ads if r.entity_level == "account")
        assert account.spend == Decimal("25.75")  # 7.50 + 10.25 + 8.00 (PMax)
        camp_ids = {r.campaign_id for r in ads if r.entity_level == "campaign"}
        assert "333" in camp_ids
        assert {c.campaign_id for c in campaigns} == {"111", "222", "333"}
        assert all(a.campaign_id != "333" for a in adgroups)  # PMax has no ad groups
        # the old ad-group-only sum silently undercounted to 17.75 (the C1 bug)
        adgroup_spend = sum((r.spend for r in ads if r.entity_level == "adgroup"), Decimal("0"))
        assert adgroup_spend == Decimal("17.75")
        assert adgroup_spend < account.spend

    def test_micros_normalized_to_decimal_currency(self):
        ads, _, _ = google_ads.map_google_ads(
            _load("google_ads_searchstream.json"), connection_id=7, company_id=3, currency="USD"
        )
        account = next(r for r in ads if r.entity_level == "account")
        # 7,500,000 + 10,250,000 + 8,000,000 micros ÷ 1e6 = 25.75 (A4)
        assert account.spend == Decimal("25.75")
        assert isinstance(account.spend, Decimal)

    def test_conversions_are_fractional_decimal(self):
        ads, _, _ = google_ads.map_google_ads(
            _load("google_ads_searchstream.json"), connection_id=7, company_id=3
        )
        account = next(r for r in ads if r.entity_level == "account")
        # 4.5 + 6.25 + 12.0 = 22.75 — Integer would truncate (A4)
        assert account.conversions == Decimal("22.75")
        assert account.conversion_value == Decimal("1514.75")  # 515.75 + 0.0 + 999.0

    def test_account_rollup_sums_volume(self):
        ads, _, _ = google_ads.map_google_ads(
            _load("google_ads_searchstream.json"), connection_id=7, company_id=3
        )
        account = next(r for r in ads if r.entity_level == "account")
        assert account.clicks == 100 + 210 + 150
        assert account.impressions == 1840 + 5400 + 3000

    def test_settling_payload_without_adgroups_yields_campaign_account_only(self):
        # include_adgroups=False (settling, A7) → empty adgroup_batches; the mapper
        # still emits campaign + account rows (conversion restatement) and no ad-groups.
        payload = _load("google_ads_searchstream.json")
        payload["adgroup_batches"] = []
        ads, _, adgroups = google_ads.map_google_ads(payload, connection_id=7, company_id=3)
        assert {r.entity_level for r in ads} == {"campaign", "account"}
        assert adgroups == []
        assert next(r for r in ads if r.entity_level == "account").spend == Decimal("25.75")

    def test_campaign_dims_carry_normalized_status(self):
        _, campaigns, _ = google_ads.map_google_ads(
            _load("google_ads_searchstream.json"), connection_id=7, company_id=3
        )
        by_id = {c.campaign_id: c for c in campaigns}
        assert by_id["111"].status == "enabled" and by_id["111"].raw_status == "ENABLED"
        assert by_id["222"].status == "removed" and by_id["222"].raw_status == "REMOVED"
        assert by_id["111"].name == "Brand Search"
        assert by_id["333"].name == "Performance Max - Retail"

    def test_adgroup_dims_link_to_campaign(self):
        _, _, adgroups = google_ads.map_google_ads(
            _load("google_ads_searchstream.json"), connection_id=7, company_id=3
        )
        by_id = {a.adgroup_id: a for a in adgroups}
        assert by_id["911"].campaign_id == "111"
        assert by_id["912"].status == "paused"

    def test_empty_results_guard(self):
        # GENUINE empty (E5): the fetcher always lands campaign_batches/adgroup_batches;
        # empty batch lists are zero data, not drift → [].
        for empty in (
            {"campaign_batches": [], "adgroup_batches": []},
            {"campaign_batches": [{"results": []}], "adgroup_batches": [{"results": []}]},
        ):
            ads, campaigns, adgroups = google_ads.map_google_ads(empty, connection_id=7, company_id=3)
            assert ads == [] and campaigns == [] and adgroups == []


# ── Meta Ads (to_money not micros, adset→campaign→account rollup, purchases) ──
class TestMetaAdsMapper:
    def test_emits_adgroup_campaign_account_levels(self):
        ads, campaigns, adgroups = meta_ads.map_meta_ads(
            _load("meta_ads_insights.json"), connection_id=7, company_id=3, currency="USD"
        )
        levels = {r.entity_level for r in ads}
        assert levels == {"adgroup", "campaign", "account"}
        assert sum(r.entity_level == "adgroup" for r in ads) == 3  # 3 ad sets
        assert sum(r.entity_level == "campaign" for r in ads) == 2  # campaigns 100, 200
        account = [r for r in ads if r.entity_level == "account"]
        assert len(account) == 1
        assert account[0].campaign_id is None and account[0].adgroup_id is None  # A2

    def test_spend_is_currency_decimal_not_micros(self):
        ads, _, _ = meta_ads.map_meta_ads(
            _load("meta_ads_insights.json"), connection_id=7, company_id=3, currency="USD"
        )
        account = next(r for r in ads if r.entity_level == "account")
        # 10.00 + 5.50 + 8.00 parsed as currency (NOT divided by 1e6, A4)
        assert account.spend == Decimal("23.50")
        assert account.spend == money.to_money("23.50")

    def test_purchases_picked_by_priority_never_summed(self):
        ads, _, _ = meta_ads.map_meta_ads(
            _load("meta_ads_insights.json"), connection_id=7, company_id=3, currency="USD"
        )
        account = next(r for r in ads if r.entity_level == "account")
        # 3 (omni) + 1 (purchase) + 2 (omni) = 6 — landing_page_view is NOT counted
        assert account.conversions == Decimal("6")
        assert account.conversion_value == Decimal("390.00")  # 150 + 40 + 200
        # adset 21 carries BOTH omni_purchase(2/200) and purchase(5/333): the priority
        # pick takes omni only — never summed (would be 7 / 533).
        adset21 = next(r for r in ads if r.entity_level == "adgroup" and r.adgroup_id == "21")
        assert adset21.conversions == Decimal("2")
        assert adset21.conversion_value == Decimal("200")

    def test_reach_only_at_adset_grain_not_rolled_up(self):
        ads, _, _ = meta_ads.map_meta_ads(
            _load("meta_ads_insights.json"), connection_id=7, company_id=3, currency="USD"
        )
        adset = next(r for r in ads if r.entity_level == "adgroup" and r.adgroup_id == "11")
        assert adset.reach == 800 and adset.purchases == Decimal("3")
        # reach is non-additive → None on the campaign + account roll-ups
        assert all(r.reach is None for r in ads if r.entity_level in ("campaign", "account"))

    def test_dims_normalized_status(self):
        _, campaigns, adgroups = meta_ads.map_meta_ads(
            _load("meta_ads_insights.json"), connection_id=7, company_id=3
        )
        camp = {c.campaign_id: c for c in campaigns}
        assert camp["100"].status == "active" and camp["100"].name == "Prospecting"
        assert camp["200"].status == "paused" and camp["200"].raw_status == "PAUSED"
        ag = {a.adgroup_id: a for a in adgroups}
        assert ag["12"].status == "paused" and ag["12"].campaign_id == "100"  # ADSET_PAUSED → paused

    def test_empty_result_guard(self):
        ads, campaigns, adgroups = meta_ads.map_meta_ads(
            _load("meta_ads_insights_empty.json"), connection_id=7, company_id=3
        )
        assert ads == [] and campaigns == [] and adgroups == []

    def test_conversion_value_falls_back_to_purchase_roas(self):
        # M-2: value-optimized / Advantage+ accounts report revenue via purchase_roas,
        # not action_values — derive value = roas × spend so it's not a silent $0.
        payload = {
            "insights": [{
                "date_start": "2026-06-01", "campaign_id": "1", "adset_id": "9",
                "spend": "100.00", "impressions": "10", "clicks": "5",
                "actions": [{"action_type": "omni_purchase", "value": "4"}],
                "action_values": [],  # no value reported here
                "purchase_roas": [{"action_type": "omni_purchase", "value": "2.5"}],
            }],
            "campaigns": [], "adsets": [],
        }
        ads, _, _ = meta_ads.map_meta_ads(payload, connection_id=7, company_id=3, currency="USD")
        adset = next(r for r in ads if r.entity_level == "adgroup")
        assert adset.conversions == Decimal("4")
        assert adset.conversion_value == Decimal("250")  # roas 2.5 × spend 100

    def test_missing_insights_envelope_raises_drift(self):
        for drifted in ({}, {"error": {"code": 190}}, {"insights": {"data": []}}):
            with pytest.raises(UnmappableShapeError):
                meta_ads.map_meta_ads(drifted, connection_id=7, company_id=3)

    def test_row_missing_adset_id_raises_drift(self):
        drifted = {"insights": [{"date_start": "2026-06-01", "campaign_id": "100", "spend": "1.00"}]}
        with pytest.raises(UnmappableShapeError):
            meta_ads.map_meta_ads(drifted, connection_id=7, company_id=3)


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
        # H7: keyEvents is GA4's conversion metric, carried in key_events ONLY — the
        # `conversions` column (for ad platforms) stays None so the two never blend.
        assert first.conversions is None
        assert first.is_data_golden is True  # H3: the fixture is golden
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

    def test_breakdown_missing_dimension_header_raises_drift(self):
        # CRITICAL-1: a 2xx report with rows but the requested breakdown header
        # dropped (drift) must RAISE, not collapse every row to dimension_value=""
        # and land as a silent success — symmetric with the GSC breakdown guard.
        from src.marketing.ingest.http_client import UnmappableShapeError

        payload = {
            "dimensionHeaders": [{"name": "date"}],  # pagePath header missing
            "metricHeaders": [{"name": "sessions"}],
            "rows": [{"dimensionValues": [{"value": "20260601"}], "metricValues": [{"value": "5"}]}],
        }
        with pytest.raises(UnmappableShapeError):
            ga4.map_ga4(payload, connection_id=5, company_id=9, dimension_type="page")
        with pytest.raises(UnmappableShapeError):
            ga4.map_ga4(payload, connection_id=5, company_id=9, dimension_type="channel")

    def test_breakdown_empty_report_does_not_raise(self):
        # a genuinely-empty report (no rows) returns [] even for a breakdown shape.
        assert (
            ga4.map_ga4(
                {"dimensionHeaders": [], "metricHeaders": [], "rows": []},
                connection_id=5, company_id=9, dimension_type="page",
            )
            == []
        )

    def test_page_query_sets_pagepath_dimension_value(self):
        # Phase 3: date × pagePath → dimension_type='page', dimension_value=pagePath.
        rows = ga4.map_ga4(
            _load("ga4_runreport_pages.json"), connection_id=5, company_id=9, dimension_type="page"
        )
        assert all(r.dimension_type == "page" for r in rows)
        assert {r.dimension_value for r in rows} == {"/", "/products"}
        # per-date grain preserved (two days for "/") so the daily re-fetch restates.
        home = sorted((r for r in rows if r.dimension_value == "/"), key=lambda r: r.date)
        assert [r.date for r in home] == [date(2026, 6, 1), date(2026, 6, 2)]
        assert home[0].sessions == 620 and home[0].users == 540

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
        # GENUINE empty (E5): a valid runReport envelope (headers/metadata present)
        # with zero rows is no-traffic, not drift → [].
        assert ga4.map_ga4({"rows": []}, connection_id=5, company_id=9, dimension_type="total") == []
        assert (
            ga4.map_ga4(
                {"metadata": {}, "dimensionHeaders": [], "metricHeaders": []},
                connection_id=5, company_id=9, dimension_type="total",
            )
            == []
        )

    def test_data_loss_from_other_row_marks_not_golden(self):
        # H3: a "(other)" overflow (dataLossFromOtherRow) flags every row not-golden
        # so the read layer can disclose the breakdown may not tie out to totals.
        payload = _load("ga4_runreport_channels.json")
        payload.setdefault("metadata", {})["dataLossFromOtherRow"] = True
        rows = ga4.map_ga4(payload, connection_id=5, company_id=9, dimension_type="channel")
        assert rows and all(r.is_data_golden is False for r in rows)

    def test_data_golden_false_marks_not_golden(self):
        payload = _load("ga4_runreport_total.json")
        payload.setdefault("metadata", {})["dataGolden"] = False
        rows = ga4.map_ga4(payload, connection_id=5, company_id=9, dimension_type="total")
        assert rows and all(r.is_data_golden is False for r in rows)


class TestGa4Fetch:
    class _PagingSeam:
        """Returns queued pages so the offset loop (H4) can be exercised offline."""

        def __init__(self, pages: list[dict]):
            self._pages = pages
            self.calls = 0

        async def post(self, url, json, *, headers=None):
            page = self._pages[min(self.calls, len(self._pages) - 1)]
            self.calls += 1
            return page

        async def get(self, url, params=None):  # pragma: no cover - unused
            return {}

    async def test_offset_loop_concatenates_pages(self):
        full = [{"dimensionValues": [{"value": "20260601"}], "metricValues": [{"value": "1"}]}] * ga4._PAGE_LIMIT
        tail = [{"dimensionValues": [{"value": "20260602"}], "metricValues": [{"value": "1"}]}]
        seam = self._PagingSeam([
            {"dimensionHeaders": [{"name": "date"}], "metricHeaders": [{"name": "sessions"}], "rows": full},
            {"dimensionHeaders": [{"name": "date"}], "metricHeaders": [{"name": "sessions"}], "rows": tail},
        ])
        merged = await ga4.fetch_ga4_total(
            seam, property_id="P", window_start=date(2026, 6, 1), window_end=date(2026, 6, 2)
        )
        assert len(merged["rows"]) == ga4._PAGE_LIMIT + 1  # both pages concatenated
        assert seam.calls == 2  # stopped after the short page

    async def test_body_requests_property_quota(self):
        body = ga4._body(["sessions"], [{"name": "date"}], date(2026, 6, 1), date(2026, 6, 2))
        assert body["returnPropertyQuota"] is True  # H8


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
        # GENUINE empty (E5): the fetcher always lands {"rows": [...]}; an empty list
        # is a site with no search traffic that day, not drift → [].
        assert gsc.map_gsc({"rows": []}, connection_id=2, company_id=4) == []

    def test_query_dimension_sets_dimension_value(self):
        # Phase 3: [date, query] → dimension_type='query', dimension_value=query.
        rows = gsc.map_gsc(
            _load("gsc_searchanalytics_query.json"), connection_id=2, company_id=4, dimension_type="query"
        )
        assert all(r.dimension_type == "query" and r.source == "gsc" for r in rows)
        assert {r.dimension_value for r in rows} == {"best widgets", "widget store near me"}
        # per-date grain (two days for "best widgets") → daily re-fetch restates.
        bw = sorted((r for r in rows if r.dimension_value == "best widgets"), key=lambda r: r.date)
        assert [r.date for r in bw] == [date(2026, 6, 1), date(2026, 6, 2)]
        assert bw[0].clicks == 40 and bw[0].impressions == 900

    def test_page_dimension_sets_dimension_value(self):
        rows = gsc.map_gsc(
            _load("gsc_searchanalytics_page.json"), connection_id=2, company_id=4, dimension_type="page"
        )
        assert all(r.dimension_type == "page" for r in rows)
        assert "https://www.example-client.com/products" in {r.dimension_value for r in rows}

    def test_breakdown_row_missing_dimension_key_raises_drift(self):
        # A [date]-only row arriving where [date, dim] was requested is a drifted
        # shape, not empty data → raise (CRITICAL-1) rather than silently mis-map.
        from src.marketing.ingest.http_client import UnmappableShapeError

        with pytest.raises(UnmappableShapeError):
            gsc.map_gsc(
                {"rows": [{"keys": ["2026-06-01"], "clicks": 1, "impressions": 2}]},
                connection_id=2, company_id=4, dimension_type="query",
            )

    def test_long_page_value_truncated_to_column_width(self):
        long_url = "https://x.com/" + "a" * 600
        rows = gsc.map_gsc(
            {"rows": [{"keys": ["2026-06-01", long_url], "clicks": 1, "impressions": 2, "ctr": 0.5, "position": 1.0}]},
            connection_id=2, company_id=4, dimension_type="page",
        )
        assert len(rows[0].dimension_value) == 512


# ── Social (organic IG/FB) ────────────────────────────────────────────────────
class TestSocialMapper:
    def test_maps_insights_to_per_metric_per_date_rows(self):
        from src.marketing.ingest import social

        rows = social.map_social_insights(
            _load("instagram_insights.json"), connection_id=3, company_id=7, platform="instagram"
        )
        # 3 metrics × 2 days = 6 rows; all tagged with the platform.
        assert len(rows) == 6
        assert all(r.platform == "instagram" and r.connection_id == 3 for r in rows)
        # follower_count is per-date (the daily series), latest day = 5412.
        fc = sorted((r for r in rows if r.metric_key == "follower_count"), key=lambda r: r.date)
        assert [r.date for r in fc] == [date(2026, 6, 2), date(2026, 6, 3)]
        assert fc[-1].value == Decimal("5412")

    def test_facebook_metrics_map(self):
        from src.marketing.ingest import social

        rows = social.map_social_insights(
            _load("facebook_insights.json"), connection_id=4, company_id=7, platform="facebook"
        )
        assert {r.metric_key for r in rows} == {
            "page_impressions_unique", "page_post_engagements", "page_fans", "page_views_total"
        }

    def test_missing_data_envelope_raises_drift(self):
        from src.marketing.ingest import social
        from src.marketing.ingest.http_client import UnmappableShapeError

        with pytest.raises(UnmappableShapeError):
            social.map_social_insights(
                {"error": {"code": 190}}, connection_id=3, company_id=7, platform="instagram"
            )

    def test_skips_breakdown_shaped_values(self):
        from src.marketing.ingest import social

        payload = {
            "data": [
                {"name": "reach", "period": "day", "values": [
                    {"value": {"city": 5}, "end_time": "2026-06-02T07:00:00+0000"},  # breakdown dict → skipped
                    {"value": 100, "end_time": "2026-06-03T07:00:00+0000"},
                ]},
            ]
        }
        rows = social.map_social_insights(payload, connection_id=3, company_id=7, platform="instagram")
        assert len(rows) == 1 and rows[0].value == Decimal("100")

    def test_empty_data_returns_empty(self):
        from src.marketing.ingest import social

        assert social.map_social_insights(
            {"data": []}, connection_id=3, company_id=7, platform="instagram"
        ) == []

    def test_renamed_values_key_raises_drift(self):
        # CRITICAL-1: a Graph rename ('values' → 'value') is drift, not no-data — it
        # must raise rather than silently emit zero rows + a green success.
        from src.marketing.ingest import social
        from src.marketing.ingest.http_client import UnmappableShapeError

        payload = {
            "data": [
                {"name": "reach", "period": "day", "value": [{"value": 5, "end_time": "2026-06-02T07:00:00+0000"}]}
            ]
        }
        with pytest.raises(UnmappableShapeError):
            social.map_social_insights(payload, connection_id=3, company_id=7, platform="instagram")

    def test_scalar_value_missing_end_time_raises_drift(self):
        from src.marketing.ingest import social
        from src.marketing.ingest.http_client import UnmappableShapeError

        payload = {"data": [{"name": "reach", "period": "day", "values": [{"value": 5}]}]}  # no end_time
        with pytest.raises(UnmappableShapeError):
            social.map_social_insights(payload, connection_id=3, company_id=7, platform="instagram")

    def test_empty_values_list_is_no_data_not_drift(self):
        # an empty values list is legitimate no-data (E5) → no row, no raise.
        from src.marketing.ingest import social

        payload = {"data": [{"name": "reach", "period": "day", "values": []}]}
        assert social.map_social_insights(payload, connection_id=3, company_id=7, platform="instagram") == []


class TestSocialFetch:
    class _Seam:
        def __init__(self, payload):
            self._p = payload

        async def get(self, url, params=None):
            return self._p

        async def post(self, url, params=None):  # pragma: no cover - unused
            return {}

    async def test_fetch_raises_on_error_envelope(self):
        # Fetch-boundary drift guard: an error/renamed envelope raises before landing.
        from src.marketing.ingest import social
        from src.marketing.ingest.http_client import UnmappableShapeError

        with pytest.raises(UnmappableShapeError):
            await social.fetch_social_insights(
                self._Seam({"error": {"code": 190}}), object_id="1", metrics=("reach",),
                window_start=date(2026, 6, 1), window_end=date(2026, 6, 2), platform="instagram",
            )

    async def test_fetch_returns_payload_on_valid_data(self):
        from src.marketing.ingest import social

        out = await social.fetch_social_insights(
            self._Seam({"data": []}), object_id="1", metrics=("reach",),
            window_start=date(2026, 6, 1), window_end=date(2026, 6, 2), platform="instagram",
        )
        assert out == {"data": []}


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

    def test_missing_lighthouse_result_raises_drift(self):
        # PageSpeed has no legitimately-empty case (a reachable URL always scores),
        # so a payload without lighthouseResult is an error/drift → partial, not [].
        with pytest.raises(UnmappableShapeError):
            pagespeed.map_pagespeed(
                {}, connection_id=8, company_id=1, captured_date=date(2026, 6, 2), strategy="mobile"
            )

    def test_missing_category_yields_none(self):
        payload = {"lighthouseResult": {"finalUrl": "https://x.test/", "categories": {}, "audits": {}}}
        rows = pagespeed.map_pagespeed(
            payload, connection_id=8, company_id=1, captured_date=date(2026, 6, 2), strategy="mobile"
        )
        assert rows[0].performance_score is None
        assert rows[0].lcp_ms is None and rows[0].cls is None


# ── Drift guard (CRITICAL-1): drifted/degraded ENVELOPE raises, never silent [] ──
class TestMapperDriftGuard:
    """A drifted/degraded API shape must RAISE UnmappableShapeError (→ run.status
    'partial') instead of mapping to [] and being recorded as a healthy zero. This
    is distinct from a genuinely-empty result (covered by each mapper's E5 test)."""

    def test_google_ads_missing_campaign_envelope_raises(self):
        # An error body / renamed envelope (no 'campaign_batches' list) — the fetcher
        # always produces it, so its absence is a contract break, not empty.
        for drifted in ({}, {"error": {"code": 7}}, {"campaign_batches": {"results": []}}):
            with pytest.raises(UnmappableShapeError):
                google_ads.map_google_ads(drifted, connection_id=7, company_id=3)

    def test_google_ads_result_missing_date_segment_raises(self):
        drifted = {"campaign_batches": [{"results": [{"campaign": {"id": "1"}, "metrics": {}}]}]}
        with pytest.raises(UnmappableShapeError):
            google_ads.map_google_ads(drifted, connection_id=7, company_id=3)

    def test_ga4_error_body_raises(self):
        # A GA4 error envelope carries none of rows/headers/metadata.
        for drifted in ({}, {"error": {"status": "INVALID_ARGUMENT"}}):
            with pytest.raises(UnmappableShapeError):
                ga4.map_ga4(drifted, connection_id=5, company_id=9, dimension_type="total")

    def test_gsc_missing_rows_envelope_raises(self):
        for drifted in ({}, {"error": {"code": 403}}):
            with pytest.raises(UnmappableShapeError):
                gsc.map_gsc(drifted, connection_id=2, company_id=4)

    def test_pagespeed_error_body_raises(self):
        with pytest.raises(UnmappableShapeError):
            pagespeed.map_pagespeed(
                {"error": {"code": 500}}, connection_id=8, company_id=1,
                captured_date=date(2026, 6, 2), strategy="mobile",
            )

    def test_drift_error_carries_platform_and_class(self):
        try:
            gsc.map_gsc({}, connection_id=2, company_id=4)
        except UnmappableShapeError as exc:
            assert exc.platform == "gsc"
            assert exc.error_class == "unmappable_shape"
        else:  # pragma: no cover - the call must raise
            raise AssertionError("expected UnmappableShapeError")
