"""Common router utilities and helpers for DRY code."""

import json as _json
from typing import Annotated, Any, NoReturn, TypeVar

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import ErrorMessages, HTTPStatus
from src.database import get_db

# Type aliases for common dependency patterns
DBSession = Annotated[AsyncSession, Depends(get_db)]


# Import at module level since circular import is now avoided
# (core/__init__.py no longer imports router_utils)
from src.auth.dependencies import get_current_active_user

# CurrentUser dependency - properly annotated with Depends
CurrentUser = Annotated[Any, Depends(get_current_active_user)]

# Generic type for entity models
T = TypeVar("T")


def parse_tag_ids(tag_ids: str | None) -> list[int] | None:
    """
    Parse a comma-separated string of tag IDs into a list of integers.

    Args:
        tag_ids: Comma-separated string of tag IDs (e.g., "1,2,3")

    Returns:
        List of integers or None if input is None/empty
    """
    if not tag_ids:
        return None
    return [int(x.strip()) for x in tag_ids.split(",") if x.strip()]


def parse_comma_separated(value: str | None) -> list[str] | None:
    """
    Parse a comma-separated string into a list of strings.

    Args:
        value: Comma-separated string (e.g., "email,call,meeting")

    Returns:
        List of strings or None if input is None/empty
    """
    if not value:
        return None
    return [x.strip() for x in value.split(",") if x.strip()]


def raise_not_found(entity_name: str, entity_id: int | None = None) -> NoReturn:
    """
    Raise an HTTPException with 404 status for entity not found.

    Args:
        entity_name: Name of the entity (e.g., "Contact", "Company")
        entity_id: Optional ID of the entity

    Raises:
        HTTPException: Always raises with 404 status
    """
    if entity_id is not None:
        detail = ErrorMessages.not_found_with_id(entity_name, entity_id)
    else:
        detail = ErrorMessages.not_found(entity_name)

    raise HTTPException(
        status_code=HTTPStatus.NOT_FOUND,
        detail=detail,
    )


def raise_bad_request(message: str) -> NoReturn:
    """
    Raise an HTTPException with 400 status for bad request.

    Args:
        message: Error message to return

    Raises:
        HTTPException: Always raises with 400 status
    """
    raise HTTPException(
        status_code=HTTPStatus.BAD_REQUEST,
        detail=message,
    )



def raise_forbidden(message: str | None = None) -> NoReturn:
    """
    Raise an HTTPException with 403 status for forbidden access.

    Args:
        message: Error message to return (defaults to "Permission denied")

    Raises:
        HTTPException: Always raises with 403 status
    """
    raise HTTPException(
        status_code=HTTPStatus.FORBIDDEN,
        detail=message or ErrorMessages.PERMISSION_DENIED,
    )


def check_ownership(entity: Any, current_user: Any, entity_name: str | None = None) -> None:
    """
    Check if the current user owns the entity (RBAC-aware).

    Superusers, admins, and managers bypass ownership checks.

    Args:
        entity: The entity to check ownership of (must have owner_id attribute)
        current_user: The current authenticated user (must have id attribute)
        entity_name: Optional entity name for error message

    Raises:
        HTTPException: 403 Forbidden if user is not the owner
    """
    if current_user.is_superuser:
        return
    user_role = getattr(current_user, 'role', 'sales_rep')
    if user_role in ('admin', 'manager'):
        return
    if entity.owner_id != current_user.id:
        message = (
            f"You do not have permission to modify this {entity_name.lower()}"
            if entity_name
            else ErrorMessages.PERMISSION_DENIED
        )
        raise_forbidden(message)


async def get_entity_or_404(  # pyright: ignore[reportInvalidTypeVarUse]
    service: Any,
    entity_id: int,
    entity_name: str,
) -> T:
    """
    Get an entity by ID or raise 404 if not found.

    Args:
        service: Service instance with get_by_id method
        entity_id: ID of the entity to fetch
        entity_name: Name of the entity for error message

    Returns:
        The entity if found

    Raises:
        HTTPException: 404 if entity not found
    """
    entity = await service.get_by_id(entity_id)
    if not entity:
        raise_not_found(entity_name, entity_id)
    return entity


def calculate_pages(total: int, page_size: int) -> int:
    """Calculate the total number of pages."""
    return (total + page_size - 1) // page_size


def parse_json_filters(filters: str | None) -> dict | None:
    """Parse a JSON filter string, raising 400 on invalid JSON."""
    if not filters:
        return None
    try:
        return _json.loads(filters)
    except _json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON filter format") from exc


def effective_owner_id(data_scope, requested_owner_id: int | None = None) -> int | None:
    """Return the effective owner_id based on data scope permissions."""
    if data_scope.can_see_all():
        return requested_owner_id
    return data_scope.owner_id


async def build_response_with_tags(service, entity, response_model, tag_brief_model):
    """Build a single entity response with tags loaded."""
    tags = await service.get_tags(entity.id)
    response_dict = response_model.model_validate(entity).model_dump()
    response_dict["tags"] = [tag_brief_model.model_validate(t) for t in tags]
    return response_model(**response_dict)


def build_list_responses_with_tags(items, tags_map, response_model, tag_brief_model) -> list:
    """Build a list of entity responses with pre-loaded tags map."""
    responses = []
    for item in items:
        response_dict = response_model.model_validate(item).model_dump()
        response_dict["tags"] = [tag_brief_model.model_validate(t) for t in tags_map.get(item.id, [])]
        responses.append(response_model(**response_dict))
    return responses
