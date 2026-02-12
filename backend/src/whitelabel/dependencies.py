"""Tenant context FastAPI dependencies for white-label system.

The middleware sets request.state.tenant_slug_hint and
request.state.tenant_domain_hint. These dependencies perform the actual
database lookup using the request-scoped DB session so that tests
(which override get_db) work correctly.
"""

from typing import Optional
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from cachetools import TTLCache

from src.database import get_db
from src.auth.dependencies import get_current_active_user
from src.auth.models import User
from src.whitelabel.models import Tenant, TenantUser
from src.whitelabel.service import TenantService

# Cache resolved tenant IDs to avoid repeated DB lookups (5 min, 100 entries)
_tenant_id_cache: TTLCache = TTLCache(maxsize=100, ttl=300)


async def get_current_tenant(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Optional[Tenant]:
    """Resolve tenant from request.state hints (set by middleware).

    Resolution order:
    1. tenant_slug_hint (from X-Tenant-Slug header)
    2. tenant_domain_hint (from Host header domain matching)
    3. Returns None if neither resolves
    """
    slug_hint = getattr(request.state, "tenant_slug_hint", None)
    domain_hint = getattr(request.state, "tenant_domain_hint", None)

    service = TenantService(db)

    if slug_hint:
        tenant = await service.get_by_slug(slug_hint)
        if tenant and tenant.is_active:
            return tenant

    if domain_hint:
        tenant = await service.get_by_domain(domain_hint)
        if tenant and tenant.is_active:
            return tenant

    return None


async def require_tenant(
    tenant: Optional[Tenant] = Depends(get_current_tenant),
) -> Tenant:
    """Require a valid tenant context, raise 400 if missing."""
    if tenant is None:
        raise HTTPException(
            status_code=400,
            detail="Tenant context required. Provide X-Tenant-Slug header or use a tenant domain.",
        )
    return tenant


async def require_tenant_admin(
    tenant: Tenant = Depends(require_tenant),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Check user is admin within this tenant.

    Superusers bypass the check. Otherwise, the user must be linked to
    the tenant with an 'admin' role.
    """
    if current_user.is_superuser:
        return current_user

    result = await db.execute(
        select(TenantUser).where(
            TenantUser.tenant_id == tenant.id,
            TenantUser.user_id == current_user.id,
        )
    )
    tenant_user = result.scalar_one_or_none()

    if not tenant_user or tenant_user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail="You must be a tenant admin to perform this action.",
        )

    return current_user
