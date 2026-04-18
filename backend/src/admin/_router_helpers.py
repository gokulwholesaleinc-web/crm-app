"""Shared helpers for admin sub-routers."""

from src.auth.models import User
from src.core.router_utils import raise_forbidden


def _require_admin(user: User) -> None:
    """Raise 403 if the user is not an admin or superuser."""
    if user.is_superuser:
        return
    if getattr(user, "role", None) == "admin":
        return
    raise_forbidden("Admin access required")
