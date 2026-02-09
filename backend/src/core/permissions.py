"""Permission dependencies for role-based access control."""

from typing import Annotated, Optional
from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.auth.dependencies import get_current_active_user
from src.auth.models import User
from src.core.constants import HTTPStatus
from src.roles.service import RoleService
from src.roles.models import RoleName


class PermissionChecker:
    """Dependency class that checks if a user has permission for an entity/action."""

    def __init__(self, entity_type: str, action: str):
        self.entity_type = entity_type
        self.action = action

    async def __call__(
        self,
        current_user: Annotated[User, Depends(get_current_active_user)],
        db: Annotated[AsyncSession, Depends(get_db)],
    ) -> User:
        # Superusers always have full access
        if current_user.is_superuser:
            return current_user

        service = RoleService(db)
        has_permission = await service.check_permission(
            current_user.id, self.entity_type, self.action
        )

        if not has_permission:
            raise HTTPException(
                status_code=HTTPStatus.FORBIDDEN,
                detail=f"You do not have permission to {self.action} {self.entity_type}",
            )

        return current_user


def require_permission(entity_type: str, action: str):
    """Create a FastAPI dependency that checks permissions.

    Usage:
        @router.post("")
        async def create_lead(
            current_user: Annotated[User, Depends(require_permission("leads", "create"))],
            ...
        ):
    """
    return PermissionChecker(entity_type, action)


async def get_user_role_name(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> str:
    """Get the role name for the current user."""
    if current_user.is_superuser:
        return RoleName.ADMIN.value
    service = RoleService(db)
    return await service.get_user_role_name(current_user.id)


async def require_admin(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Dependency that requires the user to be an admin."""
    if current_user.is_superuser:
        return current_user

    service = RoleService(db)
    role_name = await service.get_user_role_name(current_user.id)
    if role_name != RoleName.ADMIN.value:
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN,
            detail="Only admins can perform this action",
        )
    return current_user


async def require_manager_or_above(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Dependency that requires the user to be a manager or admin."""
    if current_user.is_superuser:
        return current_user

    service = RoleService(db)
    role_name = await service.get_user_role_name(current_user.id)
    if role_name not in (RoleName.ADMIN.value, RoleName.MANAGER.value):
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN,
            detail="Only managers and admins can perform this action",
        )
    return current_user


def check_record_access(entity, current_user: User, role_name: str) -> None:
    """Check if a user can access a specific record based on their role.

    - Admin/Manager: can access all records
    - Sales_rep: can only access own records (owner_id matches)
    - Viewer: read-only, handled by permission checks

    Raises HTTPException if access is denied.
    """
    if role_name in (RoleName.ADMIN.value, RoleName.MANAGER.value):
        return

    if hasattr(entity, 'owner_id') and entity.owner_id is not None:
        if entity.owner_id != current_user.id:
            raise HTTPException(
                status_code=HTTPStatus.FORBIDDEN,
                detail="You do not have permission to access this record",
            )
