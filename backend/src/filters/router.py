"""Saved filters CRUD API routes."""

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, or_, select

from src.core.constants import HTTPStatus
from src.core.data_scope import DataScope, get_data_scope
from src.core.filtering import apply_filters_to_query
from src.core.router_utils import CurrentUser, DBSession
from src.filters.models import SavedFilter
from src.filters.schemas import (
    AggregateRequest,
    AggregateResponse,
    SavedFilterCreate,
    SavedFilterResponse,
    SavedFilterUpdate,
)

router = APIRouter(prefix="/api/filters", tags=["filters"])

# Entity type to model mapping
ENTITY_MODEL_MAP = {}


def _get_entity_model(entity_type: str) -> Any:
    """Lazily load and cache entity models to avoid circular imports."""
    if not ENTITY_MODEL_MAP:
        from src.activities.models import Activity
        from src.companies.models import Company
        from src.contacts.models import Contact
        from src.leads.models import Lead
        from src.opportunities.models import Opportunity

        ENTITY_MODEL_MAP.update({
            "contacts": Contact,
            "companies": Company,
            "leads": Lead,
            "opportunities": Opportunity,
            "activities": Activity,
        })
    model = ENTITY_MODEL_MAP.get(entity_type)
    if not model:
        from src.core.router_utils import raise_bad_request
        raise_bad_request(f"Unknown entity type: {entity_type}")
    return model


def _filter_to_response(f: SavedFilter) -> SavedFilterResponse:
    """Convert a SavedFilter ORM object to a response, parsing JSON filters."""
    return SavedFilterResponse(
        id=f.id,
        name=f.name,
        entity_type=f.entity_type,
        filters=json.loads(f.filters) if isinstance(f.filters, str) else f.filters,
        user_id=f.user_id,
        is_default=f.is_default,
        is_public=f.is_public,
        created_at=f.created_at,
        updated_at=f.updated_at,
    )


@router.get("", response_model=list[SavedFilterResponse])
async def list_saved_filters(
    current_user: CurrentUser,
    db: DBSession,
    entity_type: str | None = None,
):
    """List saved filters for the current user and public filters."""
    query = select(SavedFilter).where(
        or_(
            SavedFilter.user_id == current_user.id,
            SavedFilter.is_public == True,
        )
    )
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
        is_public=data.is_public,
    )
    db.add(saved_filter)
    await db.flush()
    await db.refresh(saved_filter)

    return _filter_to_response(saved_filter)


def _apply_owner_scope(query, model, data_scope: DataScope):
    """Constrain a query to the caller's data scope via owner_id.

    Admin/manager/superuser bypass (data_scope.can_see_all() is True).
    Models without an owner_id column are rejected to avoid accidental
    leakage — an entity that cannot be owner-scoped should not be exposed
    via a raw aggregate endpoint.
    """
    if data_scope.can_see_all():
        return query
    if not hasattr(model, "owner_id"):
        from src.core.router_utils import raise_forbidden
        raise_forbidden(
            "This entity type cannot be aggregated by non-privileged users"
        )
    return query.where(model.owner_id == data_scope.owner_id)


@router.post("/aggregate", response_model=AggregateResponse)
async def aggregate_filters(
    data: AggregateRequest,
    current_user: CurrentUser,
    db: DBSession,
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
):
    """Run aggregate queries against filtered entity data.

    Supports metrics: count, sum:<field>, avg:<field>.
    Returns count, computed metrics, and first 5 matching entities.

    Sales reps only see their own records; admin/manager see everything.
    """
    model = _get_entity_model(data.entity_type)

    # Build the base filtered query for count
    count_query = select(func.count()).select_from(model)
    count_query = apply_filters_to_query(count_query, model, data.filters)
    count_query = _apply_owner_scope(count_query, model, data_scope)
    count_result = await db.execute(count_query)
    count = count_result.scalar() or 0

    # Compute metrics
    metrics: dict[str, Any] = {}
    for metric in data.metrics:
        if metric == "count":
            metrics["count"] = count
        elif ":" in metric:
            agg_func_name, field_name = metric.split(":", 1)
            column = getattr(model, field_name, None)
            if column is None:
                continue
            if agg_func_name == "sum":
                agg_query = select(func.sum(column)).select_from(model)
            elif agg_func_name == "avg":
                agg_query = select(func.avg(column)).select_from(model)
            else:
                continue
            agg_query = apply_filters_to_query(agg_query, model, data.filters)
            agg_query = _apply_owner_scope(agg_query, model, data_scope)
            agg_result = await db.execute(agg_query)
            value = agg_result.scalar()
            metrics[metric] = float(value) if value is not None else 0

    # Get sample entities (first 5)
    sample_query = select(model)
    sample_query = apply_filters_to_query(sample_query, model, data.filters)
    sample_query = _apply_owner_scope(sample_query, model, data_scope)
    sample_query = sample_query.limit(5)
    sample_result = await db.execute(sample_query)
    sample_entities = sample_result.scalars().all()

    sample_dicts = []
    for entity in sample_entities:
        entity_dict: dict[str, Any] = {"id": entity.id}
        # Add common display fields
        if hasattr(entity, "first_name"):
            entity_dict["first_name"] = entity.first_name
        if hasattr(entity, "last_name"):
            entity_dict["last_name"] = entity.last_name
        if hasattr(entity, "name"):
            entity_dict["name"] = entity.name
        if hasattr(entity, "email"):
            entity_dict["email"] = entity.email
        if hasattr(entity, "status"):
            entity_dict["status"] = entity.status
        if hasattr(entity, "company_name"):
            entity_dict["company_name"] = entity.company_name
        if hasattr(entity, "annual_revenue"):
            entity_dict["annual_revenue"] = entity.annual_revenue
        if hasattr(entity, "industry"):
            entity_dict["industry"] = entity.industry
        if hasattr(entity, "segment"):
            entity_dict["segment"] = entity.segment
        sample_dicts.append(entity_dict)

    return AggregateResponse(
        count=count,
        metrics=metrics,
        sample_entities=sample_dicts,
    )


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
    if data.is_public is not None:
        saved_filter.is_public = data.is_public

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
