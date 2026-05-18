"""Permission helpers for EntityShare-backed collaboration."""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.core.constants import HTTPStatus
from src.core.entity_types import entity_type_variants
from src.core.models import EntityShare
from src.roles.models import RoleName

VALID_SHARE_PERMISSIONS = ("view", "edit", "assignee")
WRITE_SHARE_PERMISSIONS = ("edit", "assignee")


def has_owner_or_manager_access(entity, current_user: User, role_name: str) -> bool:
    """Return True when caller can administer owner-only record actions."""
    if current_user.is_superuser:
        return True
    if role_name in (RoleName.ADMIN.value, RoleName.MANAGER.value):
        return True
    if getattr(entity, "owner_id", None) == current_user.id:
        return True
    if getattr(entity, "owner_id", None) is None:
        return getattr(entity, "created_by_id", None) == current_user.id
    return False


def require_owner_or_manager_access(
    entity,
    current_user: User,
    role_name: str,
    detail: str = "You do not have permission to manage this record",
) -> None:
    """Raise unless caller owns the record or has manager/admin scope."""
    if has_owner_or_manager_access(entity, current_user, role_name):
        return
    raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail=detail)


async def get_share_permission(
    db: AsyncSession,
    entity_type: str,
    entity_id: int,
    user_id: int,
) -> str | None:
    """Return the user's permission level for a canonical entity share."""
    result = await db.execute(
        select(EntityShare.permission_level).where(
            EntityShare.entity_type.in_(entity_type_variants(entity_type)),
            EntityShare.entity_id == entity_id,
            EntityShare.shared_with_user_id == user_id,
            EntityShare.permission_level.in_(VALID_SHARE_PERMISSIONS),
        )
    )
    permissions = set(result.scalars().all())
    if "assignee" in permissions:
        return "assignee"
    if "edit" in permissions:
        return "edit"
    if "view" in permissions:
        return "view"
    return None


async def get_writable_shared_entity_ids(
    db: AsyncSession,
    user_id: int,
    entity_type: str,
) -> set[int]:
    """Return entity IDs shared with edit-capable permissions."""
    result = await db.execute(
        select(EntityShare.entity_id).where(
            EntityShare.entity_type.in_(entity_type_variants(entity_type)),
            EntityShare.shared_with_user_id == user_id,
            EntityShare.permission_level.in_(WRITE_SHARE_PERMISSIONS),
        )
    )
    return set(result.scalars().all())


async def require_record_write_access(
    db: AsyncSession,
    entity,
    entity_type: str,
    current_user: User,
    role_name: str,
) -> None:
    """Allow owner/admin/manager or edit/assignee shares to mutate a record."""
    if has_owner_or_manager_access(entity, current_user, role_name):
        return

    permission = await get_share_permission(
        db=db,
        entity_type=entity_type,
        entity_id=entity.id,
        user_id=current_user.id,
    )
    if permission in WRITE_SHARE_PERMISSIONS:
        return

    raise HTTPException(
        status_code=HTTPStatus.FORBIDDEN,
        detail="You need edit access to modify this record",
    )
