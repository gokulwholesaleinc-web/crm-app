"""Pydantic validator coverage for tenant settings (PR #325).

Covers the tagline length cap + the social URL allowlist that
migration 034 adds. Existing URL/color validators are exercised via
the BrandingSettings PATCH path; these tests target the new fields
directly so a future change can't silently relax the constraints.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.whitelabel.schemas import (
    _TAGLINE_MAX_CHARS,
    TenantSettingsBase,
    TenantSettingsUpdate,
)


class TestTaglineValidator:
    def test_accepts_normal_tagline(self):
        s = TenantSettingsBase(
            tagline="ACCESSIBLE MEDIA | AUTHENTIC STORYTELLING | REAL RESULTS"
        )
        assert s.tagline == (
            "ACCESSIBLE MEDIA | AUTHENTIC STORYTELLING | REAL RESULTS"
        )

    def test_strips_surrounding_whitespace(self):
        s = TenantSettingsBase(tagline="   hello world   ")
        assert s.tagline == "hello world"

    def test_whitespace_only_coerced_to_none(self):
        # Consistent with the URL-field behavior: whitespace-only
        # input clears the column rather than persisting padded text.
        s = TenantSettingsBase(tagline="   ")
        assert s.tagline is None

    def test_empty_string_coerced_to_none(self):
        s = TenantSettingsBase(tagline="")
        assert s.tagline is None

    def test_none_passes_through(self):
        s = TenantSettingsBase(tagline=None)
        assert s.tagline is None

    def test_rejects_over_max_chars(self):
        # The column is VARCHAR(255); without this validator the
        # admin would see a 500 from StringDataRightTruncation
        # instead of a clean 422 explaining the field is too long.
        too_long = "A" * (_TAGLINE_MAX_CHARS + 1)
        with pytest.raises(ValidationError) as exc:
            TenantSettingsBase(tagline=too_long)
        assert "characters or fewer" in str(exc.value)

    def test_accepts_max_length_exactly(self):
        boundary = "A" * _TAGLINE_MAX_CHARS
        s = TenantSettingsBase(tagline=boundary)
        assert s.tagline == boundary

    def test_update_schema_applies_validator(self):
        # The Update schema duplicates field declarations; ensure it
        # got the validator too — otherwise PATCH /settings would
        # silently accept oversized taglines.
        with pytest.raises(ValidationError):
            TenantSettingsUpdate(tagline="A" * (_TAGLINE_MAX_CHARS + 1))


class TestSocialUrlValidator:
    @pytest.mark.parametrize(
        "field",
        [
            "social_facebook_url",
            "social_instagram_url",
            "social_tiktok_url",
            "social_linkedin_url",
            "social_youtube_url",
            "social_website_url",
        ],
    )
    def test_accepts_http_and_https(self, field: str):
        s = TenantSettingsBase(**{field: "https://example.com/x"})
        assert getattr(s, field) == "https://example.com/x"

    @pytest.mark.parametrize(
        "bad",
        [
            "javascript:alert(1)",
            "data:text/html,foo",
            "mailto:x@y.com",
            "/admin/internal",
            "ftp://example.com",
            "Javascript:alert(1)",
        ],
    )
    def test_rejects_unsafe_scheme(self, bad: str):
        with pytest.raises(ValidationError):
            TenantSettingsBase(social_facebook_url=bad)

    def test_update_schema_rejects_unsafe_scheme(self):
        with pytest.raises(ValidationError):
            TenantSettingsUpdate(social_instagram_url="javascript:alert(1)")

    def test_whitespace_only_coerced_to_none(self):
        # Mirrors the existing pattern on logo_url / privacy_url and
        # the new tagline — keeps the column-clearing semantics
        # consistent across every URL-shaped field.
        s = TenantSettingsBase(social_facebook_url="   ")
        assert s.social_facebook_url is None
