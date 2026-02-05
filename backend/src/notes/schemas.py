"""Pydantic schemas for notes."""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict


class NoteBase(BaseModel):
    content: str
    entity_type: str
    entity_id: int


class NoteCreate(NoteBase):
    pass


class NoteUpdate(BaseModel):
    content: Optional[str] = None


class NoteResponse(NoteBase):
    id: int
    created_by_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    # Include author info if available
    author_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class NoteListResponse(BaseModel):
    items: List[NoteResponse]
    total: int
    page: int
    page_size: int
    pages: int
