"""Authentication API routes."""

from typing import Annotated, List
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_db
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

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_data: UserCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Register a new user."""
    service = AuthService(db)

    # Check if user already exists
    existing_user = await service.get_user_by_email(user_data.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    user = await service.create_user(user_data)
    return user


@router.post("/login", response_model=Token)
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Login and get access token."""
    service = AuthService(db)
    user = await service.authenticate_user(form_data.username, form_data.password)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(data={"sub": user.id})
    return Token(access_token=access_token)


@router.post("/login/json", response_model=Token)
async def login_json(
    login_data: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Login with JSON body and get access token."""
    service = AuthService(db)
    user = await service.authenticate_user(login_data.email, login_data.password)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    access_token = create_access_token(data={"sub": user.id})
    return Token(access_token=access_token)


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    """Get current user profile."""
    return current_user


@router.patch("/me", response_model=UserResponse)
async def update_me(
    user_data: UserUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Update current user profile."""
    service = AuthService(db)
    updated_user = await service.update_user(current_user, user_data)
    return updated_user


@router.get("/users", response_model=List[UserResponse])
async def list_users(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: int = 0,
    limit: int = 100,
):
    """List all users (for assignment dropdowns, etc.)."""
    service = AuthService(db)
    users = await service.get_all_users(skip=skip, limit=limit)
    return users
