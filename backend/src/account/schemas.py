"""Pydantic schemas for account-settings endpoints."""

import re
from datetime import datetime
from typing import Literal
from zoneinfo import available_timezones

from pydantic import BaseModel, ConfigDict, Field, field_validator

EmailDigest = Literal["instant", "daily_8am", "off"]
LocaleCode = Literal["en-US", "en-GB", "es-MX"]
DateFormat = Literal["MM/DD/YYYY", "DD/MM/YYYY", "YYYY-MM-DD"]
TimeFormat = Literal["12h", "24h"]
WeekStart = Literal["sunday", "monday"]
CurrencyDisplay = Literal["USD", "EUR", "GBP", "CAD"]
Theme = Literal["system", "light", "dark"]
# ``/contracts`` retired 2026-05-14 — contracts router unmounted. The
# frontend dropped it from the picker; the Literal would otherwise still
# accept the value on a direct API PATCH, letting clients persist a
# preference the UI can't surface. Legacy DB rows with
# ``default_landing='/contracts'`` are silently ignored by the frontend
# route catch-all (lands on /). Same drop pattern as ``/quotes`` in PR2.
DefaultLanding = Literal[
    "/dashboard",
    "/leads",
    "/pipeline",
    "/contacts",
    "/proposals",
]

_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_TIMEZONES = available_timezones()


class NotificationPrefsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    in_app_enabled: bool
    email_enabled: bool
    email_digest: EmailDigest
    quiet_hours_enabled: bool
    quiet_hours_start: str | None = None
    quiet_hours_end: str | None = None
    event_matrix: dict[str, dict[str, bool]] = Field(default_factory=dict)
    updated_at: datetime


class NotificationPrefsUpdate(BaseModel):
    in_app_enabled: bool | None = None
    email_enabled: bool | None = None
    email_digest: EmailDigest | None = None
    quiet_hours_enabled: bool | None = None
    quiet_hours_start: str | None = None
    quiet_hours_end: str | None = None
    event_matrix: dict[str, dict[str, bool]] | None = None

    @field_validator("quiet_hours_start", "quiet_hours_end")
    @classmethod
    def _validate_hhmm(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not _HHMM.match(v):
            raise ValueError("quiet hours must be HH:MM (00-23:00-59)")
        return v


class GuideProgressPrefs(BaseModel):
    completed_guide_ids: list[str] = Field(default_factory=list, max_length=128)
    first_run_dismissed_at: str | None = None
    disabled_at: str | None = None
    last_reset_at: str | None = None

    @field_validator("completed_guide_ids")
    @classmethod
    def _dedupe_completed_ids(cls, v: list[str]) -> list[str]:
        cleaned = {guide_id.strip() for guide_id in v if guide_id.strip()}
        for guide_id in cleaned:
            if len(guide_id) > 120:
                raise ValueError("guide id is too long")
        return sorted(cleaned)


class AccountPreferencesResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    timezone: str
    locale: str
    date_format: str
    time_format: str
    week_start: str
    currency_display: str
    theme: str
    default_landing: str
    guide_progress: GuideProgressPrefs = Field(default_factory=GuideProgressPrefs)
    updated_at: datetime


class AccountPreferencesUpdate(BaseModel):
    timezone: str | None = None
    locale: LocaleCode | None = None
    date_format: DateFormat | None = None
    time_format: TimeFormat | None = None
    week_start: WeekStart | None = None
    currency_display: CurrencyDisplay | None = None
    theme: Theme | None = None
    default_landing: DefaultLanding | None = None
    guide_progress: GuideProgressPrefs | None = None

    @field_validator("timezone")
    @classmethod
    def _validate_tz(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if v not in _TIMEZONES:
            raise ValueError(f"unknown timezone: {v}")
        return v
