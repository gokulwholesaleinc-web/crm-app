"""User model for authentication."""

from datetime import datetime
from typing import Optional
from sqlalchemy import String, Boolean, DateTime, Integer, Text, ForeignKey, func, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.database import Base
from src.core.mixins.auditable import TimestampMixin


class User(Base, TimestampMixin):
    """User model for authentication and team members."""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    # Nullable for OAuth-only accounts (Google sign-in).
    hashed_password: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)

    # OAuth identity (currently only Google; nullable for password-only users).
    google_sub: Mapped[Optional[str]] = mapped_column(
        String(255), unique=True, nullable=True, index=True
    )
    # "password" or "google". Lets the UI show provenance and blocks password
    # reset flows on OAuth-only accounts.
    auth_provider: Mapped[str] = mapped_column(
        String(20), default="password", server_default="password", nullable=False
    )

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False)
    # False for new Google sign-ups until an admin approves. Grandfathered rows
    # (and password-created accounts) default to True via server_default.
    is_approved: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    # RBAC
    role: Mapped[str] = mapped_column(String(50), default="sales_rep", server_default="sales_rep")

    # Profile
    phone: Mapped[Optional[str]] = mapped_column(String(50))
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500))
    job_title: Mapped[Optional[str]] = mapped_column(String(100))

    # Login tracking
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Relationships
    user_roles: Mapped[list] = relationship("UserRole", backref="user", lazy="select")


class RejectedAccessEmail(Base):
    """Hard-block list for emails rejected by an admin."""
    __tablename__ = "rejected_access_emails"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    rejected_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    rejected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
