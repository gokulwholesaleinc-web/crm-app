"""Pydantic schemas for white-label system."""

from datetime import datetime
from typing import Optional, Dict, Any
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


def _validate_url_field(v: Optional[str], info: ValidationInfo) -> Optional[str]:
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
    company_name: Optional[str] = None
    logo_url: Optional[str] = None
    favicon_url: Optional[str] = None
    primary_color: str = "#6366f1"
    secondary_color: str = "#8b5cf6"
    accent_color: str = "#22c55e"
    email_from_name: Optional[str] = None
    email_from_address: Optional[str] = None
    feature_flags: Optional[str] = None
    custom_css: Optional[str] = None
    footer_text: Optional[str] = None
    privacy_policy_url: Optional[str] = None
    terms_of_service_url: Optional[str] = None
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
    company_name: Optional[str] = None
    logo_url: Optional[str] = None
    favicon_url: Optional[str] = None
    primary_color: Optional[str] = None
    secondary_color: Optional[str] = None
    accent_color: Optional[str] = None
    email_from_name: Optional[str] = None
    email_from_address: Optional[str] = None
    feature_flags: Optional[str] = None
    custom_css: Optional[str] = None
    footer_text: Optional[str] = None
    privacy_policy_url: Optional[str] = None
    terms_of_service_url: Optional[str] = None
    default_language: Optional[str] = None
    default_timezone: Optional[str] = None
    default_currency: Optional[str] = None
    date_format: Optional[str] = None

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
    domain: Optional[str] = None
    plan: str = "starter"
    max_users: int = 5
    max_contacts: Optional[int] = None


class TenantCreate(TenantBase):
    settings: Optional[TenantSettingsCreate] = None


class TenantUpdate(BaseModel):
    name: Optional[str] = None
    domain: Optional[str] = None
    is_active: Optional[bool] = None
    plan: Optional[str] = None
    max_users: Optional[int] = None
    max_contacts: Optional[int] = None


class TenantResponse(TenantBase):
    id: int
    is_active: bool
    created_at: datetime
    settings: Optional[TenantSettingsResponse] = None

    model_config = ConfigDict(from_attributes=True)


class TenantUserBase(BaseModel):
    tenant_id: int
    user_id: int
    role: str = "member"
    is_primary: bool = False


class TenantUserCreate(TenantUserBase):
    pass


class TenantUserUpdate(BaseModel):
    role: Optional[str] = None
    is_primary: Optional[bool] = None


class TenantUserResponse(TenantUserBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


# Public config for frontend (no sensitive data)
class PublicTenantConfig(BaseModel):
    """Public configuration exposed to frontend."""
    tenant_slug: str
    company_name: Optional[str]
    logo_url: Optional[str]
    favicon_url: Optional[str]
    primary_color: str
    secondary_color: str
    accent_color: str
    footer_text: Optional[str]
    privacy_policy_url: Optional[str]
    terms_of_service_url: Optional[str]
    default_language: str
    date_format: str
    custom_css: Optional[str]
