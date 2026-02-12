"""Pydantic schemas for comments."""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict


class CommentCreate(BaseModel):
    """Schema for creating a comment."""

    content: str
    entity_type: str
    entity_id: int
    parent_id: Optional[int] = None
    is_internal: bool = False


class CommentUpdate(BaseModel):
    """Schema for updating a comment."""

    content: str


class CommentResponse(BaseModel):
    """Response schema for a comment."""

    id: int
    content: str
    entity_type: str
    entity_id: int
    parent_id: Optional[int] = None
    is_internal: bool = False
    user_id: int
    author_name: Optional[str] = None
    mentions: List[str] = []
    replies: List["CommentResponse"] = []
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CommentListResponse(BaseModel):
    """Paginated list of comments."""

    items: List[CommentResponse]
    total: int
    page: int
    page_size: int
    pages: int
