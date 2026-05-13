"""Pydantic schemas for white-label system."""

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, ValidationInfo, field_validator

# Human-readable labels for the URL fields validated below. Keeps error
# messages consistent across :class:`TenantSettingsBase` and
# :class:`TenantSettingsUpdate` without duplicating per-field validators.
_URL_FIELD_LABELS = {
    'logo_url': 'Logo URL',
    'favicon_url': 'Favicon URL',
    'privacy_policy_url': 'Privacy policy URL',
    'terms_of_service_url': 'Terms of service URL',
    # Branded-email wrapper social links (migration 034).
    'social_facebook_url': 'Facebook URL',
    'social_instagram_url': 'Instagram URL',
    'social_tiktok_url': 'TikTok URL',
    'social_linkedin_url': 'LinkedIn URL',
    'social_youtube_url': 'YouTube URL',
    'social_website_url': 'Website URL',
}

# Color fields that must be valid hex literals. Without this, an admin can
# save ``"red"``, ``"#zzz"``, or any other 1–7 char string; the row persists
# but ``setProperty`` silently drops the value at paint time and the page
# never reflects the change — a classic "save success, no visual effect"
# silent failure caught by the PR #263 trio.
_COLOR_FIELD_LABELS = {
    'primary_color': 'Primary color',
    'secondary_color': 'Secondary color',
    'accent_color': 'Accent color',
    'bg_color_light': 'Light mode background',
    'bg_color_dark': 'Dark mode background',
    'surface_color_light': 'Light mode card surface',
    'surface_color_dark': 'Dark mode card surface',
}

# Mirrors frontend/src/utils/colorValidation.ts so the validator and
# the React picker agree on what "hex" means. Deliberately rejects the
# 8-digit (#rrggbbaa) form: every color column is VARCHAR(7), so a
# 9-char value clears the regex but then 500s on UPDATE with
# StringDataRightTruncationError. The native <input type="color">
# only emits 6-digit anyway; alpha compositing is handled by the
# `withAlpha` helper on the consumer side.
_HEX_COLOR_RE = re.compile(r'^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$')


def _validate_url_field(v: str | None, info: ValidationInfo) -> str | None:
    """Validate a URL field: strip whitespace, enforce http(s) scheme, or allow None to clear.

    Case-insensitive scheme check blocks mixed-case bypasses like
    ``Javascript:`` or ``JAVASCRIPT:`` from slipping past ``startswith``.
    """
    stripped = (v or '').strip()
    if not stripped:
        return None
    if not stripped.lower().startswith(('http://', 'https://')):
        field_name = info.field_name or ''
        label = _URL_FIELD_LABELS.get(field_name, field_name)
        raise ValueError(f'{label} must start with http:// or https://')
    return stripped


_TAGLINE_MAX_CHARS = 255


def _validate_tagline_field(v: str | None, _info: ValidationInfo) -> str | None:
    """Strip the tagline and enforce the column-width ceiling.

    Without this, a tagline >255 chars sails through Pydantic and
    raises ``StringDataRightTruncationError`` on UPDATE — the admin
    sees a 500 and no field-level hint about why their copy was
    rejected. Caps at the same ``VARCHAR(255)`` width the migration
    sets on ``tenant_settings.tagline``.
    """
    if v is None:
        return None
    if not isinstance(v, str):
        raise ValueError('Tagline must be text')
    stripped = v.strip()
    if not stripped:
        return None
    if len(stripped) > _TAGLINE_MAX_CHARS:
        raise ValueError(
            f'Tagline must be {_TAGLINE_MAX_CHARS} characters or fewer'
        )
    return stripped


def _validate_color_field(v: str | None, info: ValidationInfo) -> str | None:
    """Validate a color field: strict ``#rgb``/``#rrggbb``/``#rrggbbaa`` hex.

    ``None`` is allowed on update-shaped schemas (the field stays at its
    server-side default). On the create/full schemas the field carries its
    own default so ``None`` never reaches us.
    """
    if v is None:
        return None
    if not isinstance(v, str):
        field_name = info.field_name or ''
        label = _COLOR_FIELD_LABELS.get(field_name, field_name)
        raise ValueError(f'{label} must be a hex color like #f9fafb')
    stripped = v.strip()
    if not _HEX_COLOR_RE.match(stripped):
        field_name = info.field_name or ''
        label = _COLOR_FIELD_LABELS.get(field_name, field_name)
        raise ValueError(f'{label} must be a hex color like #f9fafb')
    return stripped


class TenantSettingsBase(BaseModel):
    company_name: str | None = None
    logo_url: str | None = None
    favicon_url: str | None = None
    primary_color: str = "#6366f1"
    secondary_color: str = "#8b5cf6"
    accent_color: str = "#22c55e"
    bg_color_light: str = "#f9fafb"
    bg_color_dark: str = "#111827"
    surface_color_light: str = "#ffffff"
    surface_color_dark: str = "#1f2937"
    email_from_name: str | None = None
    email_from_address: str | None = None
    feature_flags: str | None = None
    custom_css: str | None = None
    footer_text: str | None = None
    privacy_policy_url: str | None = None
    terms_of_service_url: str | None = None
    # Branded-email wrapper extras (migration 034).
    tagline: str | None = None
    social_facebook_url: str | None = None
    social_instagram_url: str | None = None
    social_tiktok_url: str | None = None
    social_linkedin_url: str | None = None
    social_youtube_url: str | None = None
    social_website_url: str | None = None
    default_language: str = "en"
    default_timezone: str = "UTC"
    default_currency: str = "USD"
    date_format: str = "MM/DD/YYYY"

    @field_validator(*_URL_FIELD_LABELS.keys(), mode='before')
    @classmethod
    def _validate_urls(cls, v, info: ValidationInfo):
        return _validate_url_field(v, info)

    @field_validator(*_COLOR_FIELD_LABELS.keys(), mode='before')
    @classmethod
    def _validate_colors(cls, v, info: ValidationInfo):
        return _validate_color_field(v, info)

    @field_validator('tagline', mode='before')
    @classmethod
    def _validate_tagline(cls, v, info: ValidationInfo):
        return _validate_tagline_field(v, info)


class TenantSettingsCreate(TenantSettingsBase):
    pass


class TenantSettingsUpdate(BaseModel):
    company_name: str | None = None
    logo_url: str | None = None
    favicon_url: str | None = None
    primary_color: str | None = None
    secondary_color: str | None = None
    accent_color: str | None = None
    bg_color_light: str | None = None
    bg_color_dark: str | None = None
    surface_color_light: str | None = None
    surface_color_dark: str | None = None
    email_from_name: str | None = None
    email_from_address: str | None = None
    feature_flags: str | None = None
    custom_css: str | None = None
    footer_text: str | None = None
    privacy_policy_url: str | None = None
    terms_of_service_url: str | None = None
    tagline: str | None = None
    social_facebook_url: str | None = None
    social_instagram_url: str | None = None
    social_tiktok_url: str | None = None
    social_linkedin_url: str | None = None
    social_youtube_url: str | None = None
    social_website_url: str | None = None
    default_language: str | None = None
    default_timezone: str | None = None
    default_currency: str | None = None
    date_format: str | None = None

    @field_validator(*_URL_FIELD_LABELS.keys(), mode='before')
    @classmethod
    def _validate_urls(cls, v, info: ValidationInfo):
        return _validate_url_field(v, info)

    @field_validator(*_COLOR_FIELD_LABELS.keys(), mode='before')
    @classmethod
    def _validate_colors(cls, v, info: ValidationInfo):
        return _validate_color_field(v, info)

    @field_validator('tagline', mode='before')
    @classmethod
    def _validate_tagline(cls, v, info: ValidationInfo):
        return _validate_tagline_field(v, info)


class TenantSettingsResponse(TenantSettingsBase):
    id: int
    tenant_id: int

    model_config = ConfigDict(from_attributes=True)


class TenantBase(BaseModel):
    name: str
    slug: str
    domain: str | None = None
    plan: str = "starter"
    max_users: int = 5
    max_contacts: int | None = None


class TenantCreate(TenantBase):
    settings: TenantSettingsCreate | None = None


class TenantUpdate(BaseModel):
    name: str | None = None
    domain: str | None = None
    is_active: bool | None = None
    plan: str | None = None
    max_users: int | None = None
    max_contacts: int | None = None


class TenantResponse(TenantBase):
    id: int
    is_active: bool
    created_at: datetime
    settings: TenantSettingsResponse | None = None

    model_config = ConfigDict(from_attributes=True)


class TenantUserBase(BaseModel):
    tenant_id: int
    user_id: int
    role: str = "member"
    is_primary: bool = False


class TenantUserCreate(TenantUserBase):
    pass


class TenantUserUpdate(BaseModel):
    role: str | None = None
    is_primary: bool | None = None


class TenantUserResponse(TenantUserBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


# Public config for frontend (no sensitive data)
class PublicTenantConfig(BaseModel):
    """Public configuration exposed to frontend."""
    tenant_slug: str
    company_name: str | None
    logo_url: str | None
    favicon_url: str | None
    primary_color: str
    secondary_color: str
    accent_color: str
    bg_color_light: str
    bg_color_dark: str
    surface_color_light: str
    surface_color_dark: str
    footer_text: str | None
    privacy_policy_url: str | None
    terms_of_service_url: str | None
    # Email-wrapper settings — surfaced publicly because they hydrate
    # the admin branding form and are themselves intended for outbound
    # emails (no secret material). Migration 034.
    tagline: str | None = None
    social_facebook_url: str | None = None
    social_instagram_url: str | None = None
    social_tiktok_url: str | None = None
    social_linkedin_url: str | None = None
    social_youtube_url: str | None = None
    social_website_url: str | None = None
    default_language: str
    date_format: str
    custom_css: str | None
