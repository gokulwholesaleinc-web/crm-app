"""Authentication service layer."""

from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.auth.models import User
from src.auth.schemas import UserCreate, UserUpdate
from src.auth.security import get_password_hash, verify_password


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_user_by_email(self, email: str) -> Optional[User]:
        """Get user by email address."""
        result = await self.db.execute(
            select(User).where(User.email == email)
        )
        return result.scalar_one_or_none()

    async def get_user_by_id(self, user_id: int) -> Optional[User]:
        """Get user by ID."""
        result = await self.db.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def create_user(self, user_data: UserCreate) -> User:
        """Create a new user."""
        user = User(
            email=user_data.email,
            hashed_password=get_password_hash(user_data.password),
            full_name=user_data.full_name,
            phone=user_data.phone,
            job_title=user_data.job_title,
        )
        self.db.add(user)
        await self.db.flush()
        await self.db.refresh(user)
        return user

    async def update_user(self, user: User, user_data: UserUpdate) -> User:
        """Update user profile."""
        update_data = user_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(user, field, value)
        await self.db.flush()
        await self.db.refresh(user)
        return user

    async def authenticate_user(self, email: str, password: str) -> Optional[User]:
        """Authenticate a user by email and password."""
        user = await self.get_user_by_email(email)
        if not user:
            return None
        if not verify_password(password, user.hashed_password):
            return None

        # Update last login
        user.last_login = datetime.now(timezone.utc)
        await self.db.flush()

        return user

    async def get_all_users(self, skip: int = 0, limit: int = 100) -> list[User]:
        """Get all users with pagination."""
        result = await self.db.execute(
            select(User)
            .where(User.is_active == True)
            .offset(skip)
            .limit(limit)
            .order_by(User.full_name)
        )
        return list(result.scalars().all())
