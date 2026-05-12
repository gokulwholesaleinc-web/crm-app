"""Role service layer for RBAC operations."""

import logging

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.roles.models import DEFAULT_PERMISSIONS, Role, RoleName, UserRole
from src.roles.schemas import RoleCreate, RoleUpdate

logger = logging.getLogger(__name__)


class LastAdminError(Exception):
    """Raised when an assignment would leave the tenant with no active admins."""


class RoleService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_all_roles(self) -> list[Role]:
        result = await self.db.execute(
            select(Role).order_by(Role.name)
        )
        return list(result.scalars().all())

    async def get_role_by_id(self, role_id: int) -> Role | None:
        result = await self.db.execute(
            select(Role).where(Role.id == role_id)
        )
        return result.scalar_one_or_none()

    async def get_role_by_name(self, name: str) -> Role | None:
        result = await self.db.execute(
            select(Role).where(Role.name == name)
        )
        return result.scalar_one_or_none()

    async def create_role(self, data: RoleCreate) -> Role:
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
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(role, field, value)
        await self.db.flush()
        await self.db.refresh(role)
        return role

    async def delete_role(self, role: Role) -> None:
        await self.db.delete(role)
        await self.db.flush()

    async def assign_role_to_user(self, user_id: int, role_id: int) -> UserRole:
        """Assign a role to a user. Replaces any existing role.

        Raises LastAdminError if this assignment would leave the tenant
        without any active admin (demoting the sole remaining admin).
        """
        new_role = await self.get_role_by_id(role_id)
        new_role_is_admin = bool(new_role and new_role.name == RoleName.ADMIN.value)

        if not new_role_is_admin:
            await self._guard_last_active_admin(user_id)

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

    async def _guard_last_active_admin(self, user_id: int) -> None:
        """Refuse a non-admin reassignment that would drain the last admin.

        Only guards when the *target* user currently resolves to admin.
        Counts both user_roles-table admins and legacy users.role-column
        admins so the check matches :meth:`get_user_role_name`'s fallback.
        """
        from src.auth.models import User

        target_role = await self.get_user_role_name(user_id)
        if target_role != RoleName.ADMIN.value:
            return

        admin_role = await self.get_role_by_name(RoleName.ADMIN.value)
        if admin_role is None:
            # The admin Role row should always exist (seeded at startup). If it
            # doesn't, we can't authoritatively answer "who else is admin?" via
            # the user_roles table; refuse rather than risk demoting the last
            # column-only admin silently.
            raise LastAdminError(
                "Admin role record is missing — cannot verify remaining admins. "
                "Re-seed default roles before changing admin assignments.",
            )

        admin_subq = select(UserRole.user_id).where(UserRole.role_id == admin_role.id)
        admin_predicate = or_(
            User.id.in_(admin_subq),
            User.role == RoleName.ADMIN.value,
        )

        result = await self.db.execute(
            select(User.id).where(
                User.is_active.is_(True),
                User.id != user_id,
                admin_predicate,
            )
        )
        if not result.scalars().first():
            raise LastAdminError(
                "Cannot demote the last active admin. Assign another active "
                "admin before changing this user's role.",
            )

    async def get_user_role(self, user_id: int) -> UserRole | None:
        result = await self.db.execute(
            select(UserRole)
            .options(selectinload(UserRole.role))
            .where(UserRole.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_user_role_name(self, user_id: int) -> str:
        """Get the role name for a user.

        Checks user_roles table first, falls back to the role column
        on the users table, then defaults to 'sales_rep'.
        """
        user_role = await self.get_user_role(user_id)
        if user_role and user_role.role:
            return user_role.role.name
        # Fallback: check the role column on the users table
        from src.auth.models import User
        result = await self.db.execute(
            select(User.role).where(User.id == user_id)
        )
        user_role_col = result.scalar_one_or_none()
        if user_role_col and user_role_col in (r.value for r in RoleName):
            return user_role_col
        return RoleName.SALES_REP.value

    async def get_user_permissions(self, user_id: int) -> dict:
        """Get the effective permissions for a user based on their role.

        Source-of-truth order — must match :meth:`get_user_role_name` so the
        Settings → "Your Permissions" display and the route-level enforcement
        agree:

        1. ``user_roles`` row (with optional custom ``permissions`` JSON
           override on the Role record),
        2. legacy ``users.role`` column (DEFAULT_PERMISSIONS for the matching
           RoleName),
        3. ``sales_rep`` fallback.
        """
        user_role = await self.get_user_role(user_id)
        if user_role and user_role.role:
            # ``permissions is not None`` (not truthy) so an admin who
            # intentionally locks a role down with ``{}`` doesn't silently
            # inherit the default matrix and grant full CRUD anyway.
            if user_role.role.permissions is not None:
                return user_role.role.permissions
            try:
                role_name = RoleName(user_role.role.name)
            except ValueError:
                return {}
            return DEFAULT_PERMISSIONS.get(role_name, {})

        # Column fallback: mirror get_user_role_name's second pass so a user
        # whose role lives only on users.role still gets matching permissions.
        from src.auth.models import User
        result = await self.db.execute(
            select(User.role).where(User.id == user_id)
        )
        column_role = result.scalar_one_or_none()
        if column_role:
            try:
                role_name = RoleName(column_role)
            except ValueError:
                logger.warning(
                    "users.role=%r for user_id=%s is not a known RoleName; "
                    "falling back to sales_rep permissions",
                    column_role,
                    user_id,
                )
            else:
                return DEFAULT_PERMISSIONS.get(role_name, {})

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
