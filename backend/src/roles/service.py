"""Role service layer for RBAC operations."""

from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.roles.models import Role, UserRole, RoleName, DEFAULT_PERMISSIONS
from src.roles.schemas import RoleCreate, RoleUpdate


class RoleService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_all_roles(self) -> list[Role]:
        """Get all roles."""
        result = await self.db.execute(
            select(Role).order_by(Role.name)
        )
        return list(result.scalars().all())

    async def get_role_by_id(self, role_id: int) -> Optional[Role]:
        """Get a role by ID."""
        result = await self.db.execute(
            select(Role).where(Role.id == role_id)
        )
        return result.scalar_one_or_none()

    async def get_role_by_name(self, name: str) -> Optional[Role]:
        """Get a role by name."""
        result = await self.db.execute(
            select(Role).where(Role.name == name)
        )
        return result.scalar_one_or_none()

    async def create_role(self, data: RoleCreate) -> Role:
        """Create a new role."""
        role = Role(
            name=data.name,
            description=data.description,
            permissions=data.permissions or {},
        )
        self.db.add(role)
        await self.db.flush()
        await self.db.refresh(role)
        return role

    async def update_role(self, role: Role, data: RoleUpdate) -> Role:
        """Update an existing role."""
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(role, field, value)
        await self.db.flush()
        await self.db.refresh(role)
        return role

    async def delete_role(self, role: Role) -> None:
        """Delete a role."""
        await self.db.delete(role)
        await self.db.flush()

    async def assign_role_to_user(self, user_id: int, role_id: int) -> UserRole:
        """Assign a role to a user. Replaces any existing role."""
        # Remove existing role assignments for this user
        existing = await self.db.execute(
            select(UserRole).where(UserRole.user_id == user_id)
        )
        for ur in existing.scalars().all():
            await self.db.delete(ur)

        # Create new assignment
        user_role = UserRole(user_id=user_id, role_id=role_id)
        self.db.add(user_role)
        await self.db.flush()
        await self.db.refresh(user_role)
        return user_role

    async def get_user_role(self, user_id: int) -> Optional[UserRole]:
        """Get the role assigned to a user."""
        result = await self.db.execute(
            select(UserRole)
            .options(selectinload(UserRole.role))
            .where(UserRole.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_user_role_name(self, user_id: int) -> str:
        """Get the role name for a user. Returns 'sales_rep' as default."""
        user_role = await self.get_user_role(user_id)
        if user_role and user_role.role:
            return user_role.role.name
        return RoleName.SALES_REP.value

    async def get_user_permissions(self, user_id: int) -> dict:
        """Get the effective permissions for a user based on their role."""
        user_role = await self.get_user_role(user_id)
        if user_role and user_role.role:
            # Use role's custom permissions if set, otherwise use defaults
            if user_role.role.permissions:
                return user_role.role.permissions
            role_name = RoleName(user_role.role.name)
            return DEFAULT_PERMISSIONS.get(role_name, {})
        # Default to sales_rep permissions
        return DEFAULT_PERMISSIONS[RoleName.SALES_REP]

    async def check_permission(
        self, user_id: int, entity_type: str, action: str
    ) -> bool:
        """Check if a user has a specific permission."""
        permissions = await self.get_user_permissions(user_id)
        entity_permissions = permissions.get(entity_type, [])
        return action in entity_permissions

    async def seed_default_roles(self) -> list[Role]:
        """Seed default roles if they don't exist."""
        roles = []
        descriptions = {
            RoleName.ADMIN: "Full access to all resources and settings",
            RoleName.MANAGER: "Full access to team records, read-only on settings",
            RoleName.SALES_REP: "CRUD own records, read-only on shared resources",
            RoleName.VIEWER: "Read-only access to all resources",
        }

        for role_name in RoleName:
            existing = await self.get_role_by_name(role_name.value)
            if not existing:
                role = Role(
                    name=role_name.value,
                    description=descriptions.get(role_name, ""),
                    permissions=DEFAULT_PERMISSIONS.get(role_name, {}),
                )
                self.db.add(role)
                roles.append(role)

        if roles:
            await self.db.flush()
            for role in roles:
                await self.db.refresh(role)

        return roles
