"""Common router utilities and helpers for DRY code."""

from typing import Annotated, Optional, List, TypeVar, Any
from fastapi import Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_db
from src.core.constants import HTTPStatus, ErrorMessages


# Type aliases for common dependency patterns
DBSession = Annotated[AsyncSession, Depends(get_db)]


# Import at module level since circular import is now avoided
# (core/__init__.py no longer imports router_utils)
from src.auth.dependencies import get_current_active_user

# CurrentUser dependency - properly annotated with Depends
CurrentUser = Annotated[Any, Depends(get_current_active_user)]

# Generic type for entity models
T = TypeVar("T")


def parse_tag_ids(tag_ids: Optional[str]) -> Optional[List[int]]:
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


def parse_comma_separated(value: Optional[str]) -> Optional[List[str]]:
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


def raise_not_found(entity_name: str, entity_id: int = None) -> None:
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


def raise_bad_request(message: str) -> None:
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


def raise_conflict(message: str) -> None:
    """
    Raise an HTTPException with 409 status for conflict.

    Args:
        message: Error message to return

    Raises:
        HTTPException: Always raises with 409 status
    """
    raise HTTPException(
        status_code=HTTPStatus.CONFLICT,
        detail=message,
    )


def raise_forbidden(message: str = None) -> None:
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


def check_ownership(entity: Any, current_user: Any, entity_name: str = None) -> None:
    """
    Check if the current user owns the entity.

    Args:
        entity: The entity to check ownership of (must have owner_id attribute)
        current_user: The current authenticated user (must have id attribute)
        entity_name: Optional entity name for error message

    Raises:
        HTTPException: 403 Forbidden if user is not the owner
    """
    if entity.owner_id != current_user.id:
        message = (
            f"You do not have permission to modify this {entity_name.lower()}"
            if entity_name
            else ErrorMessages.PERMISSION_DENIED
        )
        raise_forbidden(message)


async def get_entity_or_404(
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
    """
    Calculate the total number of pages.

    Args:
        total: Total number of items
        page_size: Items per page

    Returns:
        Total number of pages
    """
    return (total + page_size - 1) // page_size


# Common query parameter factories
def pagination_params(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
) -> dict:
    """
    Common pagination query parameters.

    Returns:
        Dictionary with page and page_size
    """
    return {"page": page, "page_size": page_size}


# Type alias for pagination dependency
PaginationParams = Annotated[dict, Depends(pagination_params)]
