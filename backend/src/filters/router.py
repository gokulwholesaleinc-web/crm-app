"""Saved filters CRUD API routes."""

import json
from typing import List, Optional
from fastapi import APIRouter, Query
from sqlalchemy import select, func

from src.core.router_utils import DBSession, CurrentUser
from src.core.constants import HTTPStatus
from src.filters.models import SavedFilter
from src.filters.schemas import SavedFilterCreate, SavedFilterUpdate, SavedFilterResponse

router = APIRouter(prefix="/api/filters", tags=["filters"])


def _filter_to_response(f: SavedFilter) -> SavedFilterResponse:
    """Convert a SavedFilter ORM object to a response, parsing JSON filters."""
    return SavedFilterResponse(
        id=f.id,
        name=f.name,
        entity_type=f.entity_type,
        filters=json.loads(f.filters) if isinstance(f.filters, str) else f.filters,
        user_id=f.user_id,
        is_default=f.is_default,
        created_at=f.created_at,
        updated_at=f.updated_at,
    )


@router.get("", response_model=List[SavedFilterResponse])
async def list_saved_filters(
    current_user: CurrentUser,
    db: DBSession,
    entity_type: Optional[str] = None,
):
    """List saved filters for the current user."""
    query = select(SavedFilter).where(SavedFilter.user_id == current_user.id)
    if entity_type:
        query = query.where(SavedFilter.entity_type == entity_type)
    query = query.order_by(SavedFilter.name)

    result = await db.execute(query)
    filters = result.scalars().all()

    return [_filter_to_response(f) for f in filters]


@router.post("", response_model=SavedFilterResponse, status_code=HTTPStatus.CREATED)
async def create_saved_filter(
    data: SavedFilterCreate,
    current_user: CurrentUser,
    db: DBSession,
):
    """Create a new saved filter."""
    saved_filter = SavedFilter(
        name=data.name,
        entity_type=data.entity_type,
        filters=json.dumps(data.filters),
        user_id=current_user.id,
        is_default=data.is_default,
    )
    db.add(saved_filter)
    await db.flush()
    await db.refresh(saved_filter)

    return _filter_to_response(saved_filter)


@router.get("/{filter_id}", response_model=SavedFilterResponse)
async def get_saved_filter(
    filter_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Get a saved filter by ID."""
    result = await db.execute(
        select(SavedFilter).where(
            SavedFilter.id == filter_id,
            SavedFilter.user_id == current_user.id,
        )
    )
    saved_filter = result.scalar_one_or_none()
    if not saved_filter:
        from src.core.router_utils import raise_not_found
        raise_not_found("Saved filter", filter_id)

    return _filter_to_response(saved_filter)


@router.patch("/{filter_id}", response_model=SavedFilterResponse)
async def update_saved_filter(
    filter_id: int,
    data: SavedFilterUpdate,
    current_user: CurrentUser,
    db: DBSession,
):
    """Update a saved filter."""
    result = await db.execute(
        select(SavedFilter).where(
            SavedFilter.id == filter_id,
            SavedFilter.user_id == current_user.id,
        )
    )
    saved_filter = result.scalar_one_or_none()
    if not saved_filter:
        from src.core.router_utils import raise_not_found
        raise_not_found("Saved filter", filter_id)

    if data.name is not None:
        saved_filter.name = data.name
    if data.filters is not None:
        saved_filter.filters = json.dumps(data.filters)
    if data.is_default is not None:
        saved_filter.is_default = data.is_default

    await db.flush()
    await db.refresh(saved_filter)

    return _filter_to_response(saved_filter)


@router.delete("/{filter_id}", status_code=HTTPStatus.NO_CONTENT)
async def delete_saved_filter(
    filter_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Delete a saved filter."""
    result = await db.execute(
        select(SavedFilter).where(
            SavedFilter.id == filter_id,
            SavedFilter.user_id == current_user.id,
        )
    )
    saved_filter = result.scalar_one_or_none()
    if not saved_filter:
        from src.core.router_utils import raise_not_found
        raise_not_found("Saved filter", filter_id)

    await db.delete(saved_filter)
    await db.flush()
