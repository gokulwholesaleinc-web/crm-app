"""Pydantic schemas for white-label system."""

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
}


def _validate_url_field(v: str | None, info: ValidationInfo) -> str | None:
    """Validate a URL field: strip whitespace, enforce http(s) scheme, or allow None to clear.

    Case-insensitive scheme check blocks mixed-case bypasses like
    ``Javascript:`` or ``JAVASCRIPT:`` from slipping past ``startswith``.
    """
    stripped = (v or '').strip()
    if not stripped:
        return None
    if not stripped.lower().startswith(('http://', 'https://')):
        label = _URL_FIELD_LABELS.get(info.field_name, info.field_name)
        raise ValueError(f'{label} must start with http:// or https://')
    return stripped


class TenantSettingsBase(BaseModel):
    company_name: str | None = None
    logo_url: str | None = None
    favicon_url: str | None = None
    primary_color: str = "#6366f1"
    secondary_color: str = "#8b5cf6"
    accent_color: str = "#22c55e"
    email_from_name: str | None = None
    email_from_address: str | None = None
    feature_flags: str | None = None
    custom_css: str | None = None
    footer_text: str | None = None
    privacy_policy_url: str | None = None
    terms_of_service_url: str | None = None
    default_language: str = "en"
    default_timezone: str = "UTC"
    default_currency: str = "USD"
    date_format: str = "MM/DD/YYYY"

    @field_validator(*_URL_FIELD_LABELS.keys(), mode='before')
    @classmethod
    def _validate_urls(cls, v, info: ValidationInfo):
        return _validate_url_field(v, info)


class TenantSettingsCreate(TenantSettingsBase):
    pass


class TenantSettingsUpdate(BaseModel):
    company_name: str | None = None
    logo_url: str | None = None
    favicon_url: str | None = None
    primary_color: str | None = None
    secondary_color: str | None = None
    accent_color: str | None = None
    email_from_name: str | None = None
    email_from_address: str | None = None
    feature_flags: str | None = None
    custom_css: str | None = None
    footer_text: str | None = None
    privacy_policy_url: str | None = None
    terms_of_service_url: str | None = None
    default_language: str | None = None
    default_timezone: str | None = None
    default_currency: str | None = None
    date_format: str | None = None

    @field_validator(*_URL_FIELD_LABELS.keys(), mode='before')
    @classmethod
    def _validate_urls(cls, v, info: ValidationInfo):
        return _validate_url_field(v, info)


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
    footer_text: str | None
    privacy_policy_url: str | None
    terms_of_service_url: str | None
    default_language: str
    date_format: str
    custom_css: str | None
