"""Permission utilities for RBAC."""

from src.auth.dependencies import get_current_active_user


def require_permission(resource: str, action: str = "read"):
    """Return a dependency that checks user permissions.

    Currently a passthrough - returns the current user without additional checks.
    """
    return get_current_active_user
