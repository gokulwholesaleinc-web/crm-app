"""Role management API routes (admin-only)."""

from typing import List
from fastapi import APIRouter, HTTPException

from src.core.constants import HTTPStatus
from src.core.router_utils import DBSession, CurrentUser, raise_not_found, raise_forbidden
from src.roles.models import RoleName
from src.roles.schemas import (
    RoleCreate,
    RoleUpdate,
    RoleResponse,
    UserRoleAssign,
    UserRoleResponse,
)
from src.roles.service import RoleService

router = APIRouter(prefix="/api/roles", tags=["roles"])


async def _require_admin(current_user, db: DBSession):
    """Check that the current user is an admin."""
    service = RoleService(db)
    role_name = await service.get_user_role_name(current_user.id)
    if role_name != RoleName.ADMIN.value and not current_user.is_superuser:
        raise_forbidden("Only admins can manage roles")


@router.get("", response_model=List[RoleResponse])
async def list_roles(
    current_user: CurrentUser,
    db: DBSession,
):
    """List all roles."""
    service = RoleService(db)
    return await service.get_all_roles()


@router.post("", response_model=RoleResponse, status_code=HTTPStatus.CREATED)
async def create_role(
    role_data: RoleCreate,
    current_user: CurrentUser,
    db: DBSession,
):
    """Create a new role (admin-only)."""
    await _require_admin(current_user, db)

    service = RoleService(db)
    existing = await service.get_role_by_name(role_data.name)
    if existing:
        raise HTTPException(
            status_code=HTTPStatus.CONFLICT,
            detail=f"Role '{role_data.name}' already exists",
        )
    return await service.create_role(role_data)


@router.get("/{role_id}", response_model=RoleResponse)
async def get_role(
    role_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Get a role by ID."""
    service = RoleService(db)
    role = await service.get_role_by_id(role_id)
    if not role:
        raise_not_found("Role", role_id)
    return role


@router.patch("/{role_id}", response_model=RoleResponse)
async def update_role(
    role_id: int,
    role_data: RoleUpdate,
    current_user: CurrentUser,
    db: DBSession,
):
    """Update a role (admin-only)."""
    await _require_admin(current_user, db)

    service = RoleService(db)
    role = await service.get_role_by_id(role_id)
    if not role:
        raise_not_found("Role", role_id)
    return await service.update_role(role, role_data)


@router.delete("/{role_id}", status_code=HTTPStatus.NO_CONTENT)
async def delete_role(
    role_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Delete a role (admin-only). Cannot delete default roles."""
    await _require_admin(current_user, db)

    service = RoleService(db)
    role = await service.get_role_by_id(role_id)
    if not role:
        raise_not_found("Role", role_id)

    # Prevent deletion of default roles
    default_role_names = {r.value for r in RoleName}
    if role.name in default_role_names:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=f"Cannot delete default role '{role.name}'",
        )

    await service.delete_role(role)


@router.post("/assign", response_model=UserRoleResponse)
async def assign_role(
    assignment: UserRoleAssign,
    current_user: CurrentUser,
    db: DBSession,
):
    """Assign a role to a user (admin-only)."""
    await _require_admin(current_user, db)

    service = RoleService(db)

    # Verify role exists
    role = await service.get_role_by_id(assignment.role_id)
    if not role:
        raise_not_found("Role", assignment.role_id)

    user_role = await service.assign_role_to_user(
        assignment.user_id, assignment.role_id
    )
    return user_role


@router.get("/user/{user_id}", response_model=RoleResponse)
async def get_user_role(
    user_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Get the role assigned to a user."""
    service = RoleService(db)
    user_role = await service.get_user_role(user_id)
    if not user_role:
        # Return default sales_rep role info
        default_role = await service.get_role_by_name(RoleName.SALES_REP.value)
        if default_role:
            return default_role
        raise_not_found("Role for user", user_id)
    return user_role.role


@router.get("/me/permissions")
async def get_my_permissions(
    current_user: CurrentUser,
    db: DBSession,
):
    """Get the current user's effective permissions."""
    service = RoleService(db)
    role_name = await service.get_user_role_name(current_user.id)
    permissions = await service.get_user_permissions(current_user.id)
    return {
        "role": role_name,
        "permissions": permissions,
    }
