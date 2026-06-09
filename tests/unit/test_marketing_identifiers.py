"""A10 — canonical external_account_id normalization so one account can't be
connected twice under two spellings."""

from src.marketing.identifiers import (
    normalize_external_account_id as norm,
)
from src.marketing.identifiers import (
    normalize_manager_account_id as norm_mgr,
)


class TestNormalize:
    def test_google_ads_strips_dashes_to_ten_digits(self):
        assert norm("google_ads", "832-867-5647") == "8328675647"
        assert norm("google_ads", "832 867 5647") == "8328675647"
        assert norm("google_ads", "8328675647") == "8328675647"

    def test_ga4_strips_properties_prefix(self):
        assert norm("ga4", "properties/447532899") == "447532899"
        assert norm("ga4", "447532899") == "447532899"

    def test_meta_forces_act_prefix(self):
        assert norm("meta_ads", "1368370264529719") == "act_1368370264529719"
        assert norm("meta_ads", "act_1368370264529719") == "act_1368370264529719"

    def test_gsc_and_pagespeed_pass_through_trimmed(self):
        assert norm("gsc", "  sc-domain:example.com ") == "sc-domain:example.com"
        assert norm("pagespeed", "https://example.com/") == "https://example.com/"

    def test_manager_account_id_digits_only(self):
        assert norm_mgr("832-867-5647") == "8328675647"
        assert norm_mgr(None) is None
        assert norm_mgr("") is None
