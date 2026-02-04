"""White-label/tenant service layer."""

from typing import Optional, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from src.whitelabel.models import Tenant, TenantSettings, TenantUser
from src.whitelabel.schemas import (
    TenantCreate,
    TenantUpdate,
    TenantSettingsCreate,
    TenantSettingsUpdate,
    TenantUserCreate,
    TenantUserUpdate,
)


class TenantService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, tenant_id: int) -> Optional[Tenant]:
        """Get tenant by ID with settings."""
        result = await self.db.execute(
            select(Tenant)
            .where(Tenant.id == tenant_id)
            .options(selectinload(Tenant.settings))
        )
        return result.scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> Optional[Tenant]:
        """Get tenant by slug with settings."""
        result = await self.db.execute(
            select(Tenant)
            .where(Tenant.slug == slug)
            .options(selectinload(Tenant.settings))
        )
        return result.scalar_one_or_none()

    async def get_by_domain(self, domain: str) -> Optional[Tenant]:
        """Get tenant by custom domain."""
        result = await self.db.execute(
            select(Tenant)
            .where(Tenant.domain == domain)
            .options(selectinload(Tenant.settings))
        )
        return result.scalar_one_or_none()

    async def get_all(self, active_only: bool = True) -> List[Tenant]:
        """Get all tenants."""
        query = select(Tenant).options(selectinload(Tenant.settings))
        if active_only:
            query = query.where(Tenant.is_active == True)
        query = query.order_by(Tenant.name)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def create(self, data: TenantCreate) -> Tenant:
        """Create a new tenant with settings."""
        tenant_data = data.model_dump(exclude={"settings"})
        tenant = Tenant(**tenant_data)
        self.db.add(tenant)
        await self.db.flush()

        # Create settings
        if data.settings:
            settings = TenantSettings(
                tenant_id=tenant.id,
                **data.settings.model_dump(),
            )
        else:
            settings = TenantSettings(
                tenant_id=tenant.id,
                company_name=tenant.name,
            )
        self.db.add(settings)
        await self.db.flush()
        await self.db.refresh(tenant)

        return tenant

    async def update(self, tenant: Tenant, data: TenantUpdate) -> Tenant:
        """Update a tenant."""
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(tenant, field, value)
        await self.db.flush()
        await self.db.refresh(tenant)
        return tenant

    async def delete(self, tenant: Tenant) -> None:
        """Delete a tenant."""
        await self.db.delete(tenant)
        await self.db.flush()


class TenantSettingsService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_tenant_id(self, tenant_id: int) -> Optional[TenantSettings]:
        """Get settings for a tenant."""
        result = await self.db.execute(
            select(TenantSettings).where(TenantSettings.tenant_id == tenant_id)
        )
        return result.scalar_one_or_none()

    async def update(
        self,
        settings: TenantSettings,
        data: TenantSettingsUpdate,
    ) -> TenantSettings:
        """Update tenant settings."""
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(settings, field, value)
        await self.db.flush()
        await self.db.refresh(settings)
        return settings


class TenantUserService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_user_tenants(self, user_id: int) -> List[TenantUser]:
        """Get all tenants a user belongs to."""
        result = await self.db.execute(
            select(TenantUser).where(TenantUser.user_id == user_id)
        )
        return list(result.scalars().all())

    async def get_tenant_users(self, tenant_id: int) -> List[TenantUser]:
        """Get all users in a tenant."""
        result = await self.db.execute(
            select(TenantUser).where(TenantUser.tenant_id == tenant_id)
        )
        return list(result.scalars().all())

    async def add_user_to_tenant(self, data: TenantUserCreate) -> TenantUser:
        """Add a user to a tenant."""
        tenant_user = TenantUser(**data.model_dump())
        self.db.add(tenant_user)
        await self.db.flush()
        await self.db.refresh(tenant_user)
        return tenant_user

    async def update_user_role(
        self,
        tenant_user: TenantUser,
        data: TenantUserUpdate,
    ) -> TenantUser:
        """Update user role in tenant."""
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(tenant_user, field, value)
        await self.db.flush()
        await self.db.refresh(tenant_user)
        return tenant_user

    async def remove_user_from_tenant(self, tenant_user: TenantUser) -> None:
        """Remove user from tenant."""
        await self.db.delete(tenant_user)
        await self.db.flush()

    async def get_primary_tenant(self, user_id: int) -> Optional[TenantUser]:
        """Get user's primary tenant."""
        result = await self.db.execute(
            select(TenantUser)
            .where(TenantUser.user_id == user_id)
            .where(TenantUser.is_primary == True)
        )
        return result.scalar_one_or_none()
