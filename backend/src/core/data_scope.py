"""Data-scoping dependency for role-based record visibility.

Provides a reusable FastAPI dependency that determines which records
a user can access based on their role:
- admin/manager: see all records (owner_id filter = None)
- sales_rep/viewer: see only own records + shared records
"""

from typing import Annotated, Optional, List
from dataclasses import dataclass, field
from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.auth.dependencies import get_current_active_user
from src.auth.models import User
from src.roles.models import RoleName


@dataclass
class DataScope:
    """Encapsulates data access scope for the current user.

    Attributes:
        user_id: The authenticated user's ID.
        role_name: The user's role name string.
        owner_id: If set, filter records to this owner_id.
                  None means the user can see all records.
        is_scoped: Whether data filtering should be applied.
        shared_entity_ids: Dict of entity_type -> list of entity IDs
                          that have been shared with this user.
    """
    user_id: int
    role_name: str
    owner_id: Optional[int] = None
    is_scoped: bool = True
    shared_entity_ids: dict = field(default_factory=dict)

    def can_see_all(self) -> bool:
        """Whether this user can see all records regardless of owner."""
        return not self.is_scoped

    def get_accessible_owner_ids(self) -> Optional[List[int]]:
        """Get list of owner_ids this user can access, or None if all."""
        if not self.is_scoped:
            return None
        return [self.user_id]

    def get_shared_ids(self, entity_type: str) -> List[int]:
        """Get entity IDs shared with this user for a given entity type."""
        return self.shared_entity_ids.get(entity_type, [])


async def get_data_scope(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataScope:
    """FastAPI dependency that returns the data scope for the current user.

    Usage in routers:
        @router.get("")
        async def list_items(
            data_scope: Annotated[DataScope, Depends(get_data_scope)],
            ...
        ):
            # data_scope.owner_id is None for admin/manager
            # data_scope.owner_id is user.id for sales_rep/viewer
    """
    from src.roles.service import RoleService

    # Superusers see everything
    if current_user.is_superuser:
        return DataScope(
            user_id=current_user.id,
            role_name=RoleName.ADMIN.value,
            owner_id=None,
            is_scoped=False,
        )

    # Determine role
    role_service = RoleService(db)
    role_name = await role_service.get_user_role_name(current_user.id)

    # Admin and manager see all records
    if role_name in (RoleName.ADMIN.value, RoleName.MANAGER.value):
        return DataScope(
            user_id=current_user.id,
            role_name=role_name,
            owner_id=None,
            is_scoped=False,
        )

    # Sales rep and viewer: load shared entity IDs
    shared = {}
    try:
        from src.core.models import EntityShare
        result = await db.execute(
            select(EntityShare.entity_type, EntityShare.entity_id)
            .where(EntityShare.shared_with_user_id == current_user.id)
        )
        for entity_type, entity_id in result.all():
            shared.setdefault(entity_type, []).append(entity_id)
    except Exception:
        # EntityShare table may not exist yet during migrations
        pass

    return DataScope(
        user_id=current_user.id,
        role_name=role_name,
        owner_id=current_user.id,
        is_scoped=True,
        shared_entity_ids=shared,
    )


def check_record_access_or_shared(
    entity,
    current_user: User,
    role_name: str,
    shared_entity_ids: List[int] = None,
    entity_type: str = None,
) -> None:
    """Check if a user can access a record, considering sharing.

    Raises HTTPException if access is denied.

    Args:
        entity: The entity to check access for.
        current_user: The authenticated user.
        role_name: The user's role name.
        shared_entity_ids: List of entity IDs shared with this user.
        entity_type: The entity type for shared lookup.
    """
    from fastapi import HTTPException
    from src.core.constants import HTTPStatus

    # Admin/manager can access all
    if role_name in (RoleName.ADMIN.value, RoleName.MANAGER.value):
        return

    # Superuser can access all
    if current_user.is_superuser:
        return

    # Owner can access own records
    if hasattr(entity, 'owner_id') and entity.owner_id == current_user.id:
        return

    # Check if shared
    if shared_entity_ids and hasattr(entity, 'id'):
        if entity.id in shared_entity_ids:
            return

    raise HTTPException(
        status_code=HTTPStatus.FORBIDDEN,
        detail="You do not have permission to access this record",
    )
