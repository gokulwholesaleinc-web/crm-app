"""Authentication API routes."""

from typing import Annotated, List
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm
from src.core.constants import HTTPStatus, ErrorMessages, EntityNames
from src.core.router_utils import DBSession, CurrentUser, raise_bad_request
from src.auth.models import User
from src.auth.schemas import (
    UserCreate,
    UserUpdate,
    UserResponse,
    Token,
    LoginRequest,
)
from src.auth.service import AuthService
from src.auth.security import create_access_token
from src.auth.dependencies import get_current_active_user, get_current_superuser

from src.core.rate_limit import limiter

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse, status_code=HTTPStatus.CREATED)
@limiter.limit("3/minute")
async def register(
    request: Request,
    user_data: UserCreate,
    db: DBSession,
):
    """Register a new user."""
    service = AuthService(db)

    # Check if user already exists
    existing_user = await service.get_user_by_email(user_data.email)
    if existing_user:
        raise_bad_request("Email already registered")

    user = await service.create_user(user_data)
    return user


@router.post("/login", response_model=Token)
@limiter.limit("5/minute")
async def login(
    request: Request,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: DBSession,
):
    """Login and get access token."""
    service = AuthService(db)
    user = await service.authenticate_user(form_data.username, form_data.password)

    if not user:
        raise HTTPException(
            status_code=HTTPStatus.UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(data={"sub": str(user.id)})
    return Token(access_token=access_token)


@router.post("/login/json", response_model=Token)
@limiter.limit("5/minute")
async def login_json(
    request: Request,
    login_data: LoginRequest,
    db: DBSession,
):
    """Login with JSON body and get access token."""
    import traceback
    try:
        service = AuthService(db)
        user = await service.authenticate_user(login_data.email, login_data.password)

        if not user:
            raise HTTPException(
                status_code=HTTPStatus.UNAUTHORIZED,
                detail="Incorrect email or password",
            )

        access_token = create_access_token(data={"sub": str(user.id)})
        return Token(access_token=access_token)
    except HTTPException:
        raise
    except Exception as e:
        print(f"LOGIN ERROR: {type(e).__name__}: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Internal error: {type(e).__name__}: {e}",
        )


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: CurrentUser,
):
    """Get current user profile."""
    return current_user


@router.patch("/me", response_model=UserResponse)
async def update_me(
    user_data: UserUpdate,
    current_user: CurrentUser,
    db: DBSession,
):
    """Update current user profile."""
    service = AuthService(db)
    updated_user = await service.update_user(current_user, user_data)
    return updated_user


@router.get("/users", response_model=List[UserResponse])
async def list_users(
    current_user: CurrentUser,
    db: DBSession,
    skip: int = 0,
    limit: int = 100,
):
    """List all users (for assignment dropdowns, etc.)."""
    service = AuthService(db)
    users = await service.get_all_users(skip=skip, limit=limit)
    return users
