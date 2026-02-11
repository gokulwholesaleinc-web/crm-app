"""Sharing endpoints for record collaboration between users."""

from typing import Optional, List
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException
from sqlalchemy import select, delete

from src.core.constants import HTTPStatus
from src.core.router_utils import DBSession, CurrentUser, check_ownership
from src.core.models import EntityShare

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
    items: List[ShareResponse]


@router.post("", response_model=ShareResponse, status_code=HTTPStatus.CREATED)
async def share_entity(
    request: ShareRequest,
    current_user: CurrentUser,
    db: DBSession,
):
    """Share an entity with another user."""
    if request.permission_level not in ("view", "edit"):
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="permission_level must be 'view' or 'edit'",
        )

    if request.shared_with_user_id == current_user.id:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="Cannot share a record with yourself",
        )

    # Check if already shared
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

    # Only the sharer, the shared user, or admin/manager can revoke
    user_role = getattr(current_user, 'role', 'sales_rep')
    if (
        not current_user.is_superuser
        and user_role not in ('admin', 'manager')
        and share.shared_by_user_id != current_user.id
        and share.shared_with_user_id != current_user.id
    ):
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN,
            detail="You do not have permission to revoke this share",
        )

    await db.delete(share)
    await db.flush()
