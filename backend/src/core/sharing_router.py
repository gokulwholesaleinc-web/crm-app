"""Sharing endpoints for record collaboration between users."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import aliased

from src.audit.service import AuditService
from src.auth.models import User
from src.core.constants import HTTPStatus
from src.core.data_scope import (
    DataScope,
    check_record_access_or_shared,
    get_data_scope,
    invalidate_scope_cache,
)
from src.core.entity_access import _resolve_entity
from src.core.entity_types import canonical_singular, entity_type_variants
from src.core.models import EntityShare
from src.core.router_utils import CurrentUser, DBSession
from src.core.share_permissions import (
    VALID_SHARE_PERMISSIONS,
    require_owner_or_manager_access,
)
from src.notifications.service import NotificationService

router = APIRouter(prefix="/api/sharing", tags=["sharing"])


class ShareRequest(BaseModel):
    entity_type: str
    entity_id: int
    shared_with_user_id: int
    permission_level: str = "view"


class ShareResponse(BaseModel):
    id: int
    entity_type: str
    entity_id: int
    shared_with_user_id: int
    shared_by_user_id: int
    permission_level: str

    model_config = {"from_attributes": True}


class ShareListResponse(BaseModel):
    items: list[ShareResponse]


@router.post("", response_model=ShareResponse, status_code=HTTPStatus.CREATED)
async def share_entity(
    request: ShareRequest,
    current_user: CurrentUser,
    db: DBSession,
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
):
    """Share an entity with another user.

    Caller must own the target record or have manager/admin scope. Prevents
    view-only recipients from granting peers access or escalating permissions.
    """
    if request.permission_level not in VALID_SHARE_PERMISSIONS:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="permission_level must be 'view', 'edit', or 'assignee'",
        )

    if request.shared_with_user_id == current_user.id:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="Cannot share a record with yourself",
        )

    entity, plural = await _resolve_entity(db, request.entity_type, request.entity_id)
    if entity is None:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail=f"{request.entity_type} {request.entity_id} not found",
        )
    entity_type = plural
    require_owner_or_manager_access(
        entity,
        current_user,
        data_scope.role_name,
        detail="Only the owner, admins, and managers can share this record",
    )

    target_result = await db.execute(
        select(User.id).where(
            User.id == request.shared_with_user_id,
            User.is_active.is_(True),
        )
    )
    if target_result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail="User to share with not found",
        )

    entity_type_inputs = entity_type_variants(request.entity_type)
    existing = await db.execute(
        select(EntityShare.id)
        .where(
            EntityShare.entity_type.in_(entity_type_inputs),
            EntityShare.entity_id == request.entity_id,
            EntityShare.shared_with_user_id == request.shared_with_user_id,
        )
        .limit(1)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=HTTPStatus.CONFLICT,
            detail="This record is already shared with the specified user",
        )

    share = EntityShare(
        entity_type=entity_type,
        entity_id=request.entity_id,
        shared_with_user_id=request.shared_with_user_id,
        shared_by_user_id=current_user.id,
        permission_level=request.permission_level,
    )
    db.add(share)
    await db.flush()

    # Audit row keyed to the shared record so it surfaces in that entity's history.
    await AuditService(db).log_change(
        entity_type=canonical_singular(entity_type),
        entity_id=request.entity_id,
        user_id=current_user.id,
        action="share",
        changes=[{
            "field": "shared_with_user_id",
            "old": None,
            "new": request.shared_with_user_id,
            "permission_level": request.permission_level,
        }],
    )

    sharer_name = current_user.full_name or current_user.email
    entity_singular = canonical_singular(entity_type)
    if request.permission_level == "assignee":
        notif_type = "record_assigned_to_you"
        title = f"{sharer_name} assigned a {entity_singular} to you"
        message = f"You have been assigned a {entity_singular} (id={request.entity_id})"
    else:
        notif_type = "entity_shared_with_you"
        title = f"{sharer_name} shared a {entity_singular} with you"
        message = f"A {entity_singular} was shared with you (id={request.entity_id})"

    notif_service = NotificationService(db)
    await notif_service.create_notification(
        user_id=request.shared_with_user_id,
        type=notif_type,
        title=title,
        message=message,
        entity_type=entity_type,
        entity_id=request.entity_id,
    )

    await db.commit()
    await db.refresh(share)
    invalidate_scope_cache(request.shared_with_user_id)

    return ShareResponse.model_validate(share)


@router.get("/{entity_type}/{entity_id}", response_model=ShareListResponse)
async def list_entity_shares(
    entity_type: str,
    entity_id: int,
    current_user: CurrentUser,
    db: DBSession,
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
):
    """List all shares for a specific entity."""
    entity, plural = await _resolve_entity(db, entity_type, entity_id)
    if entity is None:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail=f"{entity_type} {entity_id} not found",
        )

    check_record_access_or_shared(
        entity,
        current_user,
        data_scope.role_name,
        shared_entity_ids=data_scope.get_shared_ids(plural),
        entity_type=plural,
    )

    entity_type_inputs = entity_type_variants(entity_type)
    result = await db.execute(
        select(EntityShare).where(
            EntityShare.entity_type.in_(entity_type_inputs),
            EntityShare.entity_id == entity_id,
        )
    )
    shares = list(result.scalars().all())
    return ShareListResponse(
        items=[ShareResponse.model_validate(s) for s in shares]
    )


@router.delete("/{share_id}", status_code=HTTPStatus.NO_CONTENT)
async def revoke_share(
    share_id: int,
    current_user: CurrentUser,
    db: DBSession,
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
):
    """Revoke a share as the sharer, recipient, or admin."""
    result = await db.execute(
        select(EntityShare).where(EntityShare.id == share_id)
    )
    share = result.scalar_one_or_none()
    if not share:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail="Share not found",
        )

    if (
        not current_user.is_superuser
        and data_scope.role_name != "admin"
        and current_user.id not in (share.shared_by_user_id, share.shared_with_user_id)
    ):
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN,
            detail="You do not have permission to revoke this share",
        )

    shared_with_id = share.shared_with_user_id
    revoked_entity_type = share.entity_type
    revoked_entity_id = share.entity_id
    revoked_permission = share.permission_level
    await db.delete(share)
    await db.flush()

    # Mirror audit row for the unshare event, same keying as POST /api/sharing.
    await AuditService(db).log_change(
        entity_type=canonical_singular(revoked_entity_type),
        entity_id=revoked_entity_id,
        user_id=current_user.id,
        action="unshare",
        changes=[{
            "field": "shared_with_user_id",
            "old": shared_with_id,
            "new": None,
            "permission_level": revoked_permission,
        }],
    )
    await db.commit()
    invalidate_scope_cache(shared_with_id)


# ---------------------------------------------------------------------------
# Admin listing endpoint
# ---------------------------------------------------------------------------


class AdminShareItem(BaseModel):
    id: int
    entity_type: str
    entity_id: int
    shared_with_user_id: int
    shared_with_user_name: str
    shared_with_user_email: str
    shared_by_user_id: int
    shared_by_user_name: str
    permission_level: str
    created_at: datetime

    model_config = {"from_attributes": True}


class AdminShareListResponse(BaseModel):
    items: list[AdminShareItem]
    total: int
    page: int
    page_size: int


@router.get("/admin", response_model=AdminShareListResponse)
async def admin_list_shares(
    current_user: CurrentUser,
    db: DBSession,
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
    entity_type: str | None = Query(None),
    shared_with_user_id: int | None = Query(None),
    shared_by_user_id: int | None = Query(None),
    permission_level: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    """List all EntityShare rows for admins."""
    if not current_user.is_superuser and data_scope.role_name != "admin":
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN,
            detail="Only admins can access this endpoint",
        )

    SharedWith = aliased(User)
    SharedBy = aliased(User)

    base_query = (
        select(
            EntityShare.id,
            EntityShare.entity_type,
            EntityShare.entity_id,
            EntityShare.shared_with_user_id,
            SharedWith.full_name.label("shared_with_user_name"),
            SharedWith.email.label("shared_with_user_email"),
            EntityShare.shared_by_user_id,
            SharedBy.full_name.label("shared_by_user_name"),
            EntityShare.permission_level,
            EntityShare.created_at,
        )
        .join(SharedWith, EntityShare.shared_with_user_id == SharedWith.id)
        .join(SharedBy, EntityShare.shared_by_user_id == SharedBy.id)
    )

    if entity_type is not None:
        base_query = base_query.where(
            EntityShare.entity_type.in_(entity_type_variants(entity_type))
        )
    if shared_with_user_id is not None:
        base_query = base_query.where(EntityShare.shared_with_user_id == shared_with_user_id)
    if shared_by_user_id is not None:
        base_query = base_query.where(EntityShare.shared_by_user_id == shared_by_user_id)
    if permission_level is not None:
        base_query = base_query.where(EntityShare.permission_level == permission_level)

    count_query = select(func.count()).select_from(base_query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    offset = (page - 1) * page_size
    rows_result = await db.execute(
        base_query.order_by(EntityShare.created_at.desc()).offset(offset).limit(page_size)
    )
    rows = rows_result.all()

    items = [
        AdminShareItem(
            id=row.id,
            entity_type=row.entity_type,
            entity_id=row.entity_id,
            shared_with_user_id=row.shared_with_user_id,
            shared_with_user_name=row.shared_with_user_name,
            shared_with_user_email=row.shared_with_user_email,
            shared_by_user_id=row.shared_by_user_id,
            shared_by_user_name=row.shared_by_user_name,
            permission_level=row.permission_level,
            created_at=row.created_at,
        )
        for row in rows
    ]

    return AdminShareListResponse(items=items, total=total, page=page, page_size=page_size)
