"""Sharing endpoints for record collaboration between users."""


import logging
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
from src.core.entity_access import _resolve_entity, canonical_singular
from src.core.models import EntityShare
from src.core.router_utils import CurrentUser, DBSession
from src.notifications.service import NotificationService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sharing", tags=["sharing"])

# Singular form for notification copy and audit-row keying comes from
# canonical_singular (core.entity_access), which knows every shareable
# entity type. A local dict drifts (PR #266 missed activity/payment/expense,
# leaking shared activities to be audit-keyed under "activities" while the
# rest of the codebase queries history under "activity").


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

    Caller must be able to access the target record (owner, share recipient,
    admin, or manager). Prevents reps from granting peers access to records
    they themselves cannot see.
    """
    if request.permission_level not in ("view", "edit", "assignee"):
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
    check_record_access_or_shared(
        entity,
        current_user,
        data_scope.role_name,
        shared_entity_ids=data_scope.get_shared_ids(plural),
        entity_type=plural,
    )

    existing = await db.execute(
        select(EntityShare).where(
            EntityShare.entity_type == request.entity_type,
            EntityShare.entity_id == request.entity_id,
            EntityShare.shared_with_user_id == request.shared_with_user_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=HTTPStatus.CONFLICT,
            detail="This record is already shared with the specified user",
        )

    share = EntityShare(
        entity_type=request.entity_type,
        entity_id=request.entity_id,
        shared_with_user_id=request.shared_with_user_id,
        shared_by_user_id=current_user.id,
        permission_level=request.permission_level,
    )
    db.add(share)
    await db.flush()
    await db.refresh(share)
    invalidate_scope_cache(request.shared_with_user_id)

    # Audit row keyed to the shared record so it surfaces in that entity's history.
    try:
        await AuditService(db).log_change(
            entity_type=canonical_singular(request.entity_type),
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
    except Exception:
        logger.exception(
            "share audit log failed for entity=%s/%s shared_with=%s",
            request.entity_type, request.entity_id, request.shared_with_user_id,
        )

    sharer_name = current_user.full_name or current_user.email
    entity_singular = canonical_singular(request.entity_type)
    if request.permission_level == "assignee":
        notif_type = "record_assigned_to_you"
        title = f"{sharer_name} assigned a {entity_singular} to you"
        message = f"You have been assigned a {entity_singular} (id={request.entity_id})"
    else:
        notif_type = "entity_shared_with_you"
        title = f"{sharer_name} shared a {entity_singular} with you"
        message = f"A {entity_singular} was shared with you (id={request.entity_id})"

    try:
        notif_service = NotificationService(db)
        await notif_service.create_notification(
            user_id=request.shared_with_user_id,
            type=notif_type,
            title=title,
            message=message,
            entity_type=request.entity_type,
            entity_id=request.entity_id,
        )
    except Exception:
        logger.exception(
            "share notification failed for user_id=%s entity=%s/%s — share row was created",
            request.shared_with_user_id,
            request.entity_type,
            request.entity_id,
        )

    return ShareResponse.model_validate(share)


@router.get("/{entity_type}/{entity_id}", response_model=ShareListResponse)
async def list_entity_shares(
    entity_type: str,
    entity_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """List all shares for a specific entity."""
    result = await db.execute(
        select(EntityShare).where(
            EntityShare.entity_type == entity_type,
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
):
    """Revoke a share. Only the person who shared or an admin can revoke."""
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
        and current_user.role not in ("admin", "manager")
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
    # Invalidate scope cache so the shared-with user loses access immediately
    invalidate_scope_cache(shared_with_id)

    # Mirror audit row for the unshare event, same keying as POST /api/sharing.
    try:
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
    except Exception:
        logger.exception(
            "unshare audit log failed for share_id=%s entity=%s/%s",
            share_id, revoked_entity_type, revoked_entity_id,
        )


# ---------------------------------------------------------------------------
# Admin-only listing endpoint
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
    entity_type: str | None = Query(None),
    shared_with_user_id: int | None = Query(None),
    shared_by_user_id: int | None = Query(None),
    permission_level: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    """Admin-only: list all EntityShare rows across the system with filters."""
    if not current_user.is_superuser and current_user.role not in ("admin", "manager"):
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN,
            detail="Only admins and managers can access this endpoint",
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
        base_query = base_query.where(EntityShare.entity_type == entity_type)
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
