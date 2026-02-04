"""User model for authentication."""

from datetime import datetime
from typing import Optional
from sqlalchemy import String, Boolean, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from src.database import Base
from src.core.mixins.auditable import TimestampMixin


class User(Base, TimestampMixin):
    """User model for authentication and team members."""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False)

    # Profile
    phone: Mapped[Optional[str]] = mapped_column(String(50))
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500))
    job_title: Mapped[Optional[str]] = mapped_column(String(100))

    # Login tracking
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
