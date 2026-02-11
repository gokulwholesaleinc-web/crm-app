"""Note API routes."""

from typing import Optional
from fastapi import APIRouter, Query, HTTPException
from src.core.constants import HTTPStatus, EntityNames
from src.core.router_utils import (
    DBSession,
    CurrentUser,
    get_entity_or_404,
    calculate_pages,
)
from src.notes.schemas import (
    NoteCreate,
    NoteUpdate,
    NoteResponse,
    NoteListResponse,
)
from src.notes.service import NoteService

router = APIRouter(prefix="/api/notes", tags=["notes"])


@router.get("", response_model=NoteListResponse)
async def list_notes(
    current_user: CurrentUser,
    db: DBSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
):
    """List notes with pagination and filters (scoped to current user)."""
    service = NoteService(db)

    notes, total = await service.get_list(
        page=page,
        page_size=page_size,
        entity_type=entity_type,
        entity_id=entity_id,
        created_by_id=current_user.id,
    )

    return NoteListResponse(
        items=[NoteResponse(**n) for n in notes],
        total=total,
        page=page,
        page_size=page_size,
        pages=calculate_pages(total, page_size),
    )


@router.post("", response_model=NoteResponse, status_code=HTTPStatus.CREATED)
async def create_note(
    note_data: NoteCreate,
    current_user: CurrentUser,
    db: DBSession,
):
    """Create a new note."""
    service = NoteService(db)
    note = await service.create(note_data, current_user.id)
    return NoteResponse(**note)


@router.get("/{note_id}", response_model=NoteResponse)
async def get_note(
    note_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Get a note by ID."""
    service = NoteService(db)
    note = await get_entity_or_404(service, note_id, EntityNames.NOTE)
    # Note doesn't have author_name attribute, need to fetch it
    notes, _ = await service.get_list(page=1, page_size=1, entity_type=note.entity_type, entity_id=note.entity_id)
    for n in notes:
        if n["id"] == note_id:
            return NoteResponse(**n)
    # Fallback if not found in list (shouldn't happen)
    return NoteResponse(
        id=note.id,
        content=note.content,
        entity_type=note.entity_type,
        entity_id=note.entity_id,
        created_by_id=note.created_by_id,
        created_at=note.created_at,
        updated_at=note.updated_at,
        author_name=None,
    )


@router.patch("/{note_id}", response_model=NoteResponse)
async def update_note(
    note_id: int,
    note_data: NoteUpdate,
    current_user: CurrentUser,
    db: DBSession,
):
    """Update a note."""
    service = NoteService(db)
    note = await get_entity_or_404(service, note_id, EntityNames.NOTE)

    # Only the creator can update their note
    if note.created_by_id != current_user.id:
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN,
            detail="You can only edit your own notes",
        )

    updated_note = await service.update(note, note_data, current_user.id)
    return NoteResponse(**updated_note)


@router.delete("/{note_id}", status_code=HTTPStatus.NO_CONTENT)
async def delete_note(
    note_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Delete a note."""
    service = NoteService(db)
    note = await get_entity_or_404(service, note_id, EntityNames.NOTE)

    # Only the creator can delete their note
    if note.created_by_id != current_user.id:
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN,
            detail="You can only delete your own notes",
        )

    await service.delete(note)
