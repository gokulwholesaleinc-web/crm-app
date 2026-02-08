"""Comment API routes."""

from typing import Optional
from fastapi import APIRouter, Query, HTTPException
from src.core.constants import HTTPStatus
from src.core.router_utils import DBSession, CurrentUser, calculate_pages
from src.comments.schemas import (
    CommentCreate,
    CommentUpdate,
    CommentResponse,
    CommentListResponse,
)
from src.comments.service import CommentService

router = APIRouter(prefix="/api/comments", tags=["comments"])


@router.get("", response_model=CommentListResponse)
async def list_comments(
    current_user: CurrentUser,
    db: DBSession,
    entity_type: str = Query(..., description="Entity type (e.g. opportunity, contact)"),
    entity_id: int = Query(..., description="Entity ID"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List comments for an entity with pagination."""
    service = CommentService(db)

    items, total = await service.get_list(
        entity_type=entity_type,
        entity_id=entity_id,
        page=page,
        page_size=page_size,
    )

    return CommentListResponse(
        items=[CommentResponse(**item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
        pages=calculate_pages(total, page_size),
    )


@router.post("", response_model=CommentResponse, status_code=HTTPStatus.CREATED)
async def create_comment(
    comment_data: CommentCreate,
    current_user: CurrentUser,
    db: DBSession,
):
    """Create a new comment."""
    service = CommentService(db)

    # If replying, verify parent comment exists
    if comment_data.parent_id:
        parent = await service.get_by_id(comment_data.parent_id)
        if not parent:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail="Parent comment not found",
            )

    comment = await service.create(
        content=comment_data.content,
        entity_type=comment_data.entity_type,
        entity_id=comment_data.entity_id,
        user_id=current_user.id,
        parent_id=comment_data.parent_id,
        is_internal=comment_data.is_internal,
    )
    return CommentResponse(**comment)


@router.get("/{comment_id}", response_model=CommentResponse)
async def get_comment(
    comment_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Get a comment by ID."""
    service = CommentService(db)
    comment = await service.get_by_id(comment_id)
    if not comment:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail="Comment not found",
        )

    comment_dict = await service._build_comment_dict(comment)
    # Get author name
    if comment.user_id:
        from sqlalchemy import select
        from src.auth.models import User
        user_result = await db.execute(
            select(User.full_name).where(User.id == comment.user_id)
        )
        comment_dict["author_name"] = user_result.scalar_one_or_none()

    return CommentResponse(**comment_dict)


@router.patch("/{comment_id}", response_model=CommentResponse)
async def update_comment(
    comment_id: int,
    comment_data: CommentUpdate,
    current_user: CurrentUser,
    db: DBSession,
):
    """Update a comment."""
    service = CommentService(db)
    comment = await service.get_by_id(comment_id)
    if not comment:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail="Comment not found",
        )

    # Only the author can edit their comment
    if comment.user_id != current_user.id:
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN,
            detail="You can only edit your own comments",
        )

    if comment_data.content is not None:
        updated = await service.update(comment, comment_data.content)
        return CommentResponse(**updated)

    # No changes
    comment_dict = await service._build_comment_dict(comment)
    return CommentResponse(**comment_dict)


@router.delete("/{comment_id}", status_code=HTTPStatus.NO_CONTENT)
async def delete_comment(
    comment_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Delete a comment."""
    service = CommentService(db)
    comment = await service.get_by_id(comment_id)
    if not comment:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail="Comment not found",
        )

    # Only the author can delete their comment
    if comment.user_id != current_user.id:
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN,
            detail="You can only delete your own comments",
        )

    await service.delete(comment)
