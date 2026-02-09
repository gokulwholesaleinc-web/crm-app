"""Comment API routes."""

from fastapi import APIRouter, Query, HTTPException
from src.core.constants import HTTPStatus
from src.core.router_utils import DBSession, CurrentUser, calculate_pages
from src.comments.schemas import (
    CommentCreate,
    CommentUpdate,
    CommentResponse,
    CommentListResponse,
)
from src.comments.service import CommentService, parse_mentions

router = APIRouter(prefix="/api/comments", tags=["comments"])


def comment_to_response(comment, mentioned_users=None) -> CommentResponse:
    """Convert a Comment model to a CommentResponse, recursively handling replies."""
    mentions = mentioned_users if mentioned_users is not None else parse_mentions(comment.content)
    replies = [comment_to_response(r) for r in (comment.replies or [])]
    return CommentResponse(
        id=comment.id,
        content=comment.content,
        entity_type=comment.entity_type,
        entity_id=comment.entity_id,
        parent_id=comment.parent_id,
        is_internal=comment.is_internal,
        user_id=comment.user_id,
        user_name=comment.user_name,
        user_email=comment.user_email,
        mentioned_users=mentions,
        replies=replies,
        created_at=comment.created_at,
        updated_at=comment.updated_at,
    )


@router.get("/{entity_type}/{entity_id}", response_model=CommentListResponse)
async def list_entity_comments(
    entity_type: str,
    entity_id: int,
    current_user: CurrentUser,
    db: DBSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List comments for an entity with pagination."""
    service = CommentService(db)
    comments, total = await service.get_entity_comments(
        entity_type=entity_type,
        entity_id=entity_id,
        page=page,
        page_size=page_size,
    )
    return CommentListResponse(
        items=[comment_to_response(c) for c in comments],
        total=total,
        page=page,
        page_size=page_size,
        pages=calculate_pages(total, page_size),
    )


@router.post("", response_model=CommentResponse, status_code=HTTPStatus.CREATED)
async def create_comment(
    data: CommentCreate,
    current_user: CurrentUser,
    db: DBSession,
):
    """Create a new comment."""
    service = CommentService(db)
    comment = await service.create(
        content=data.content,
        entity_type=data.entity_type,
        entity_id=data.entity_id,
        user_id=current_user.id,
        user_name=getattr(current_user, "full_name", None),
        user_email=getattr(current_user, "email", None),
        parent_id=data.parent_id,
        is_internal=data.is_internal,
    )
    mentions = parse_mentions(comment.content)
    return comment_to_response(comment, mentioned_users=mentions)


@router.patch("/{comment_id}", response_model=CommentResponse)
async def update_comment(
    comment_id: int,
    data: CommentUpdate,
    current_user: CurrentUser,
    db: DBSession,
):
    """Update a comment (author only)."""
    service = CommentService(db)
    comment = await service.get_by_id(comment_id)
    if not comment:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Comment not found")
    if comment.user_id != current_user.id:
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN,
            detail="You can only edit your own comments",
        )
    updated = await service.update(comment, data.content)
    return comment_to_response(updated)


@router.delete("/{comment_id}", status_code=HTTPStatus.NO_CONTENT)
async def delete_comment(
    comment_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Delete a comment (author only)."""
    service = CommentService(db)
    comment = await service.get_by_id(comment_id)
    if not comment:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Comment not found")
    if comment.user_id != current_user.id:
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN,
            detail="You can only delete your own comments",
        )
    await service.delete(comment)
