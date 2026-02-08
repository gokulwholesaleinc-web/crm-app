"""Pydantic schemas for comments."""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict


class CommentCreate(BaseModel):
    content: str
    entity_type: str
    entity_id: int
    parent_id: Optional[int] = None
    is_internal: bool = False


class CommentUpdate(BaseModel):
    content: Optional[str] = None


class CommentResponse(BaseModel):
    id: int
    content: str
    entity_type: str
    entity_id: int
    user_id: Optional[int] = None
    author_name: Optional[str] = None
    parent_id: Optional[int] = None
    is_internal: bool = False
    created_at: datetime
    updated_at: datetime
    replies: List["CommentResponse"] = []
    mentions: List[str] = []

    model_config = ConfigDict(from_attributes=True)


class CommentListResponse(BaseModel):
    items: List[CommentResponse]
    total: int
    page: int
    page_size: int
    pages: int
