"""Authentication dependencies for FastAPI."""

from typing import Annotated
from cachetools import TTLCache
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import make_transient
from src.database import get_db
from src.auth.models import User
from src.auth.security import decode_token
from src.auth.service import AuthService

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/google/authorize")

_user_cache: TTLCache = TTLCache(maxsize=500, ttl=30)


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Get the current authenticated user from JWT token."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = decode_token(token)
    if payload is None:
        raise credentials_exception

    user_id_str = payload.get("sub")
    if user_id_str is None:
        raise credentials_exception

    try:
        user_id = int(user_id_str)
    except (ValueError, TypeError):
        raise credentials_exception

    cached = _user_cache.get(user_id)
    if cached is not None:
        return cached

    service = AuthService(db)
    user = await service.get_user_by_id(user_id)
    if user is None:
        raise credentials_exception

    # Detach from session before caching to prevent DetachedInstanceError
    db.expunge(user)
    make_transient(user)
    _user_cache[user_id] = user
    return user


def invalidate_user_cache(user_id: int) -> None:
    """Remove a user from the auth cache (call on deactivation/role change)."""
    _user_cache.pop(user_id, None)


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Ensure the current user is active."""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
        )
    return current_user


async def get_current_superuser(
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> User:
    """Ensure the current user is a superuser or has admin role."""
    if not current_user.is_superuser and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough privileges",
        )
    return current_user
