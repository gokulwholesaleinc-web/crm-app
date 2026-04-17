"""Pydantic schemas for notes."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NoteBase(BaseModel):
    content: str
    entity_type: str
    entity_id: int


class NoteCreate(NoteBase):
    pass


class NoteUpdate(BaseModel):
    content: str | None = None


class NoteResponse(NoteBase):
    id: int
    created_by_id: int | None = None
    created_at: datetime
    updated_at: datetime
    # Include author info if available
    author_name: str | None = None

    model_config = ConfigDict(from_attributes=True)


class NoteListResponse(BaseModel):
    items: list[NoteResponse]
    total: int
    page: int
    page_size: int
    pages: int
