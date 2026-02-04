"""White-label/tenant API routes."""

from typing import Annotated, List
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_db
from src.auth.models import User
from src.auth.dependencies import get_current_active_user, get_current_superuser
from src.whitelabel.models import Tenant, TenantSettings
from src.whitelabel.schemas import (
    TenantCreate,
    TenantUpdate,
    TenantResponse,
    TenantSettingsUpdate,
    TenantSettingsResponse,
    TenantUserCreate,
    TenantUserUpdate,
    TenantUserResponse,
    PublicTenantConfig,
)
from src.whitelabel.service import TenantService, TenantSettingsService, TenantUserService

router = APIRouter(prefix="/api/tenants", tags=["tenants"])


# Public endpoint to get tenant config by slug/domain
@router.get("/config/{slug}", response_model=PublicTenantConfig)
async def get_public_config(
    slug: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Get public tenant configuration (no auth required)."""
    service = TenantService(db)
    tenant = await service.get_by_slug(slug)

    if not tenant or not tenant.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )

    settings = tenant.settings
    return PublicTenantConfig(
        tenant_slug=tenant.slug,
        company_name=settings.company_name if settings else tenant.name,
        logo_url=settings.logo_url if settings else None,
        favicon_url=settings.favicon_url if settings else None,
        primary_color=settings.primary_color if settings else "#6366f1",
        secondary_color=settings.secondary_color if settings else "#8b5cf6",
        accent_color=settings.accent_color if settings else "#22c55e",
        footer_text=settings.footer_text if settings else None,
        privacy_policy_url=settings.privacy_policy_url if settings else None,
        terms_of_service_url=settings.terms_of_service_url if settings else None,
        default_language=settings.default_language if settings else "en",
        date_format=settings.date_format if settings else "MM/DD/YYYY",
        custom_css=settings.custom_css if settings else None,
    )


@router.get("/config/domain/{domain}", response_model=PublicTenantConfig)
async def get_config_by_domain(
    domain: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Get tenant config by custom domain."""
    service = TenantService(db)
    tenant = await service.get_by_domain(domain)

    if not tenant or not tenant.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )

    settings = tenant.settings
    return PublicTenantConfig(
        tenant_slug=tenant.slug,
        company_name=settings.company_name if settings else tenant.name,
        logo_url=settings.logo_url if settings else None,
        favicon_url=settings.favicon_url if settings else None,
        primary_color=settings.primary_color if settings else "#6366f1",
        secondary_color=settings.secondary_color if settings else "#8b5cf6",
        accent_color=settings.accent_color if settings else "#22c55e",
        footer_text=settings.footer_text if settings else None,
        privacy_policy_url=settings.privacy_policy_url if settings else None,
        terms_of_service_url=settings.terms_of_service_url if settings else None,
        default_language=settings.default_language if settings else "en",
        date_format=settings.date_format if settings else "MM/DD/YYYY",
        custom_css=settings.custom_css if settings else None,
    )


# Admin endpoints (superuser only)
@router.get("", response_model=List[TenantResponse])
async def list_tenants(
    current_user: Annotated[User, Depends(get_current_superuser)],
    db: Annotated[AsyncSession, Depends(get_db)],
    active_only: bool = True,
):
    """List all tenants (superuser only)."""
    service = TenantService(db)
    tenants = await service.get_all(active_only=active_only)
    return tenants


@router.post("", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    tenant_data: TenantCreate,
    current_user: Annotated[User, Depends(get_current_superuser)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Create a new tenant (superuser only)."""
    service = TenantService(db)

    # Check if slug already exists
    existing = await service.get_by_slug(tenant_data.slug)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant slug already exists",
        )

    # Check domain if provided
    if tenant_data.domain:
        existing_domain = await service.get_by_domain(tenant_data.domain)
        if existing_domain:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Domain already in use",
            )

    tenant = await service.create(tenant_data)
    return tenant


@router.get("/{tenant_id}", response_model=TenantResponse)
async def get_tenant(
    tenant_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Get a tenant by ID."""
    service = TenantService(db)
    tenant = await service.get_by_id(tenant_id)

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )

    return tenant


@router.patch("/{tenant_id}", response_model=TenantResponse)
async def update_tenant(
    tenant_id: int,
    tenant_data: TenantUpdate,
    current_user: Annotated[User, Depends(get_current_superuser)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Update a tenant (superuser only)."""
    service = TenantService(db)
    tenant = await service.get_by_id(tenant_id)

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )

    updated_tenant = await service.update(tenant, tenant_data)
    return updated_tenant


@router.delete("/{tenant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tenant(
    tenant_id: int,
    current_user: Annotated[User, Depends(get_current_superuser)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Delete a tenant (superuser only)."""
    service = TenantService(db)
    tenant = await service.get_by_id(tenant_id)

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )

    await service.delete(tenant)


# Settings endpoints
@router.get("/{tenant_id}/settings", response_model=TenantSettingsResponse)
async def get_tenant_settings(
    tenant_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Get tenant settings."""
    service = TenantSettingsService(db)
    settings = await service.get_by_tenant_id(tenant_id)

    if not settings:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Settings not found",
        )

    return settings


@router.patch("/{tenant_id}/settings", response_model=TenantSettingsResponse)
async def update_tenant_settings(
    tenant_id: int,
    settings_data: TenantSettingsUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Update tenant settings."""
    service = TenantSettingsService(db)
    settings = await service.get_by_tenant_id(tenant_id)

    if not settings:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Settings not found",
        )

    updated_settings = await service.update(settings, settings_data)
    return updated_settings


# Tenant Users endpoints
@router.get("/{tenant_id}/users", response_model=List[TenantUserResponse])
async def list_tenant_users(
    tenant_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """List users in a tenant."""
    service = TenantUserService(db)
    users = await service.get_tenant_users(tenant_id)
    return users


@router.post("/{tenant_id}/users", response_model=TenantUserResponse, status_code=status.HTTP_201_CREATED)
async def add_user_to_tenant(
    tenant_id: int,
    user_data: TenantUserCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Add a user to a tenant."""
    # Ensure tenant_id matches
    user_data.tenant_id = tenant_id

    service = TenantUserService(db)
    tenant_user = await service.add_user_to_tenant(user_data)
    return tenant_user


@router.delete("/{tenant_id}/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_user_from_tenant(
    tenant_id: int,
    user_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Remove a user from a tenant."""
    service = TenantUserService(db)
    users = await service.get_tenant_users(tenant_id)

    tenant_user = None
    for u in users:
        if u.user_id == user_id:
            tenant_user = u
            break

    if not tenant_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found in tenant",
        )

    await service.remove_user_from_tenant(tenant_user)
