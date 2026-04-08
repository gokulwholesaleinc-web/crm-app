"""Authentication service layer."""

from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
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

    async def get_user_by_google_sub(self, google_sub: str) -> Optional[User]:
        """Get user by Google subject identifier."""
        result = await self.db.execute(
            select(User).where(User.google_sub == google_sub)
        )
        return result.scalar_one_or_none()

    async def upsert_google_user(
        self,
        *,
        google_sub: str,
        email: str,
        full_name: str,
        avatar_url: Optional[str] = None,
    ) -> User:
        """Find or create a user from a verified Google profile.

        Resolution order:
        1. Existing user with matching google_sub → update last_login + profile.
        2. Existing user with matching email → link google_sub, mark provider.
        3. Otherwise → create a new OAuth-only account (no password).

        Handles a race where two concurrent sign-in callbacks for the same
        brand-new email both miss the SELECT and try to INSERT: the loser
        catches IntegrityError, rolls back to a savepoint, re-queries, and
        returns whichever row the winner created.
        """
        existing = await self.get_user_by_google_sub(google_sub)
        if existing:
            existing.last_login = datetime.now(timezone.utc)
            if avatar_url and not existing.avatar_url:
                existing.avatar_url = avatar_url
            await self.db.flush()
            return existing

        existing_by_email = await self.get_user_by_email(email)
        if existing_by_email:
            return await self._link_google_to_existing(
                existing_by_email,
                google_sub=google_sub,
                avatar_url=avatar_url,
            )

        new_user = User(
            email=email,
            hashed_password=None,
            full_name=full_name or email.split("@")[0],
            google_sub=google_sub,
            auth_provider="google",
            avatar_url=avatar_url,
            last_login=datetime.now(timezone.utc),
            is_active=True,
        )
        # Use a SAVEPOINT so an IntegrityError (unique email / google_sub
        # collision from a concurrent callback) doesn't poison the outer
        # transaction. The loser re-queries and returns the winning row.
        try:
            async with self.db.begin_nested():
                self.db.add(new_user)
                await self.db.flush()
        except IntegrityError:
            winner_by_sub = await self.get_user_by_google_sub(google_sub)
            if winner_by_sub:
                return winner_by_sub
            winner_by_email = await self.get_user_by_email(email)
            if winner_by_email:
                return await self._link_google_to_existing(
                    winner_by_email,
                    google_sub=google_sub,
                    avatar_url=avatar_url,
                )
            # No row to recover — re-raise so the router returns a clear 4xx.
            raise

        await self.db.refresh(new_user)
        return new_user

    async def _link_google_to_existing(
        self,
        user: User,
        *,
        google_sub: str,
        avatar_url: Optional[str] = None,
    ) -> User:
        """Attach a google_sub to an existing user row."""
        user.google_sub = google_sub
        user.last_login = datetime.now(timezone.utc)
        if not user.hashed_password:
            # No password set — this user is now OAuth-only.
            user.auth_provider = "google"
        if avatar_url and not user.avatar_url:
            user.avatar_url = avatar_url
        await self.db.flush()
        return user

    async def create_user(self, user_data: UserCreate) -> User:
        """Create a new user."""
        user = User(
            email=user_data.email,
            hashed_password=get_password_hash(user_data.password),
            full_name=user_data.full_name,
            phone=user_data.phone,
            job_title=user_data.job_title,
            auth_provider="password",
        )
        self.db.add(user)
        await self.db.flush()
        await self.db.refresh(user)
        return user

    async def update_user(self, user: User, user_data: UserUpdate) -> User:
        """Update user profile."""
        user = await self.db.merge(user)
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
        # OAuth-only accounts have no password hash; reject password login
        # with a consistent failure rather than crashing verify_password.
        if not user.hashed_password:
            return None
        if not verify_password(password, user.hashed_password):
            return None

        # Update last login
        user.last_login = datetime.now(timezone.utc)
        await self.db.flush()

        return user

    async def get_all_users(self, page: int = 1, page_size: int = 100) -> list[User]:
        """Get all users with pagination."""
        offset = (page - 1) * page_size
        result = await self.db.execute(
            select(User)
            .where(User.is_active == True)
            .offset(offset)
            .limit(page_size)
            .order_by(User.full_name)
        )
        return list(result.scalars().all())
