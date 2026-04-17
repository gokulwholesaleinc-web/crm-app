"""White-label/tenant API routes."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy import select

from src.auth.dependencies import get_current_superuser
from src.core.constants import (
    DEFAULT_ACCENT_COLOR,
    DEFAULT_DATE_FORMAT,
    DEFAULT_LANGUAGE,
    DEFAULT_PRIMARY_COLOR,
    DEFAULT_SECONDARY_COLOR,
    EntityNames,
    HTTPStatus,
)
from src.core.router_utils import CurrentUser, DBSession, raise_bad_request, raise_not_found
from src.whitelabel.dependencies import require_tenant
from src.whitelabel.models import Tenant, TenantUser
from src.whitelabel.schemas import (
    PublicTenantConfig,
    TenantCreate,
    TenantResponse,
    TenantSettingsResponse,
    TenantSettingsUpdate,
    TenantUpdate,
    TenantUserCreate,
    TenantUserResponse,
)
from src.whitelabel.service import TenantService, TenantSettingsService, TenantUserService

router = APIRouter(prefix="/api/tenants", tags=["tenants"])

# Type alias for superuser dependency
SuperUser = Annotated[Any, Depends(get_current_superuser)]


async def _require_tenant_member(db, tenant_id: int, current_user) -> None:
    """Raise 403 unless the caller is a member of the given tenant.

    Superusers bypass. Used on read endpoints that return tenant config
    without requiring full admin privileges.
    """
    if current_user.is_superuser:
        return
    result = await db.execute(
        select(TenantUser).where(
            TenantUser.tenant_id == tenant_id,
            TenantUser.user_id == current_user.id,
        )
    )
    if result.scalar_one_or_none() is None:
        raise_bad_request_or_forbidden()


def raise_bad_request_or_forbidden():
    from src.core.router_utils import raise_forbidden
    raise_forbidden("You are not a member of this tenant")


def _build_public_tenant_config(tenant: Tenant) -> PublicTenantConfig:
    """Build a PublicTenantConfig from a Tenant with its settings."""
    settings = tenant.settings
    return PublicTenantConfig(
        tenant_slug=tenant.slug,
        company_name=settings.company_name if settings else tenant.name,
        logo_url=settings.logo_url if settings else None,
        favicon_url=settings.favicon_url if settings else None,
        primary_color=settings.primary_color if settings else DEFAULT_PRIMARY_COLOR,
        secondary_color=settings.secondary_color if settings else DEFAULT_SECONDARY_COLOR,
        accent_color=settings.accent_color if settings else DEFAULT_ACCENT_COLOR,
        footer_text=settings.footer_text if settings else None,
        privacy_policy_url=settings.privacy_policy_url if settings else None,
        terms_of_service_url=settings.terms_of_service_url if settings else None,
        default_language=settings.default_language if settings else DEFAULT_LANGUAGE,
        date_format=settings.date_format if settings else DEFAULT_DATE_FORMAT,
        custom_css=settings.custom_css if settings else None,
    )


# Branding endpoint using middleware-resolved tenant context
@router.get("/branding/current", response_model=PublicTenantConfig)
async def get_current_branding(
    tenant: Tenant = Depends(require_tenant),
):
    """Get branding config for the current tenant (resolved via middleware).

    No auth required. Tenant is resolved from X-Tenant-Slug header
    or Host domain by the TenantMiddleware + require_tenant dependency.
    """
    return _build_public_tenant_config(tenant)


# Public endpoint to get tenant config by slug/domain
@router.get("/config/{slug}", response_model=PublicTenantConfig)
async def get_public_config(
    slug: str,
    db: DBSession,
):
    """Get public tenant configuration (no auth required)."""
    service = TenantService(db)
    tenant = await service.get_by_slug(slug)

    if not tenant or not tenant.is_active:
        raise_not_found(EntityNames.TENANT)

    return _build_public_tenant_config(tenant)


@router.get("/config/domain/{domain}", response_model=PublicTenantConfig)
async def get_config_by_domain(
    domain: str,
    db: DBSession,
):
    """Get tenant config by custom domain."""
    service = TenantService(db)
    tenant = await service.get_by_domain(domain)

    if not tenant or not tenant.is_active:
        raise_not_found(EntityNames.TENANT)

    return _build_public_tenant_config(tenant)


# Admin endpoints (superuser only)
@router.get("", response_model=list[TenantResponse])
async def list_tenants(
    current_user: SuperUser,
    db: DBSession,
    active_only: bool = True,
):
    """List all tenants (superuser only)."""
    service = TenantService(db)
    tenants = await service.get_all(active_only=active_only)
    return tenants


@router.post("", response_model=TenantResponse, status_code=HTTPStatus.CREATED)
async def create_tenant(
    tenant_data: TenantCreate,
    current_user: SuperUser,
    db: DBSession,
):
    """Create a new tenant (superuser only)."""
    service = TenantService(db)

    # Check if slug already exists
    existing = await service.get_by_slug(tenant_data.slug)
    if existing:
        raise_bad_request("Tenant slug already exists")

    # Check domain if provided
    if tenant_data.domain:
        existing_domain = await service.get_by_domain(tenant_data.domain)
        if existing_domain:
            raise_bad_request("Domain already in use")

    tenant = await service.create(tenant_data)
    return tenant


@router.get("/{tenant_id}", response_model=TenantResponse)
async def get_tenant(
    tenant_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Get a tenant by ID. Caller must be a member of the tenant."""
    await _require_tenant_member(db, tenant_id, current_user)
    service = TenantService(db)
    tenant = await service.get_by_id(tenant_id)

    if not tenant:
        raise_not_found(EntityNames.TENANT, tenant_id)

    return tenant


@router.patch("/{tenant_id}", response_model=TenantResponse)
async def update_tenant(
    tenant_id: int,
    tenant_data: TenantUpdate,
    current_user: SuperUser,
    db: DBSession,
):
    """Update a tenant (superuser only)."""
    service = TenantService(db)
    tenant = await service.get_by_id(tenant_id)

    if not tenant:
        raise_not_found(EntityNames.TENANT, tenant_id)

    updated_tenant = await service.update(tenant, tenant_data)
    return updated_tenant


@router.delete("/{tenant_id}", status_code=HTTPStatus.NO_CONTENT)
async def delete_tenant(
    tenant_id: int,
    current_user: SuperUser,
    db: DBSession,
):
    """Delete a tenant (superuser only)."""
    service = TenantService(db)
    tenant = await service.get_by_id(tenant_id)

    if not tenant:
        raise_not_found(EntityNames.TENANT, tenant_id)

    await service.delete(tenant)


# Settings endpoints
@router.get("/{tenant_id}/settings", response_model=TenantSettingsResponse)
async def get_tenant_settings(
    tenant_id: int,
    current_user: CurrentUser,
    db: DBSession,
    response: Response,
):
    """Get tenant settings. Caller must be a member of the tenant."""
    await _require_tenant_member(db, tenant_id, current_user)
    service = TenantSettingsService(db)
    settings = await service.get_by_tenant_id(tenant_id)

    if not settings:
        raise_not_found(EntityNames.TENANT_SETTINGS)

    response.headers["Cache-Control"] = "private, max-age=300"
    return settings


@router.patch("/{tenant_id}/settings", response_model=TenantSettingsResponse)
async def update_tenant_settings(
    tenant_id: int,
    settings_data: TenantSettingsUpdate,
    current_user: SuperUser,
    db: DBSession,
):
    """Update tenant settings. Superuser only — branding config + custom_css
    is a stored-XSS surface and must not be writable by sales reps."""
    service = TenantSettingsService(db)
    settings = await service.get_by_tenant_id(tenant_id)

    if not settings:
        raise_not_found(EntityNames.TENANT_SETTINGS)

    updated_settings = await service.update(settings, settings_data)
    return updated_settings


# Tenant Users endpoints
@router.get("/{tenant_id}/users", response_model=list[TenantUserResponse])
async def list_tenant_users(
    tenant_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """List users in a tenant. Caller must be a member of the tenant."""
    await _require_tenant_member(db, tenant_id, current_user)
    service = TenantUserService(db)
    users = await service.get_tenant_users(tenant_id)
    return users


@router.post("/{tenant_id}/users", response_model=TenantUserResponse, status_code=HTTPStatus.CREATED)
async def add_user_to_tenant(
    tenant_id: int,
    user_data: TenantUserCreate,
    current_user: SuperUser,
    db: DBSession,
):
    """Add a user to a tenant. Superuser only."""
    # Ensure tenant_id matches
    user_data.tenant_id = tenant_id

    service = TenantUserService(db)
    tenant_user = await service.add_user_to_tenant(user_data)
    return tenant_user


@router.delete("/{tenant_id}/users/{user_id}", status_code=HTTPStatus.NO_CONTENT)
async def remove_user_from_tenant(
    tenant_id: int,
    user_id: int,
    current_user: SuperUser,
    db: DBSession,
):
    """Remove a user from a tenant. Superuser only."""
    service = TenantUserService(db)
    users = await service.get_tenant_users(tenant_id)

    tenant_user = None
    for u in users:
        if u.user_id == user_id:
            tenant_user = u
            break

    if not tenant_user:
        raise_not_found(EntityNames.TENANT_USER)

    await service.remove_user_from_tenant(tenant_user)
