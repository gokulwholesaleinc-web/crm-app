"""Role and permission models for RBAC."""

import enum
from typing import Optional
from sqlalchemy import String, Integer, ForeignKey, Text, JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.database import Base
from src.core.mixins.auditable import TimestampMixin


class RoleName(str, enum.Enum):
    ADMIN = "admin"
    MANAGER = "manager"
    SALES_REP = "sales_rep"
    VIEWER = "viewer"


# Default permissions for each role
DEFAULT_PERMISSIONS = {
    RoleName.ADMIN: {
        "leads": ["create", "read", "update", "delete"],
        "contacts": ["create", "read", "update", "delete"],
        "companies": ["create", "read", "update", "delete"],
        "opportunities": ["create", "read", "update", "delete"],
        "activities": ["create", "read", "update", "delete"],
        "campaigns": ["create", "read", "update", "delete"],
        "workflows": ["create", "read", "update", "delete"],
        "reports": ["create", "read", "update", "delete"],
        "settings": ["create", "read", "update", "delete"],
        "users": ["create", "read", "update", "delete"],
        "roles": ["create", "read", "update", "delete"],
    },
    RoleName.MANAGER: {
        "leads": ["create", "read", "update", "delete"],
        "contacts": ["create", "read", "update", "delete"],
        "companies": ["create", "read", "update", "delete"],
        "opportunities": ["create", "read", "update", "delete"],
        "activities": ["create", "read", "update", "delete"],
        "campaigns": ["create", "read", "update", "delete"],
        "workflows": ["create", "read", "update", "delete"],
        "reports": ["read"],
        "settings": ["read"],
        "users": ["read"],
        "roles": ["read"],
    },
    RoleName.SALES_REP: {
        "leads": ["create", "read", "update", "delete"],
        "contacts": ["create", "read", "update", "delete"],
        "companies": ["create", "read", "update", "delete"],
        "opportunities": ["create", "read", "update", "delete"],
        "activities": ["create", "read", "update", "delete"],
        "campaigns": ["read"],
        "workflows": ["read"],
        "reports": ["read"],
        "settings": ["read"],
        "users": ["read"],
        "roles": [],
    },
    RoleName.VIEWER: {
        "leads": ["read"],
        "contacts": ["read"],
        "companies": ["read"],
        "opportunities": ["read"],
        "activities": ["read"],
        "campaigns": ["read"],
        "workflows": ["read"],
        "reports": ["read"],
        "settings": ["read"],
        "users": ["read"],
        "roles": [],
    },
}


class Role(Base, TimestampMixin):
    """Role model for RBAC."""
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(String(255))
    permissions: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    # Relationships
    users: Mapped[list["UserRole"]] = relationship("UserRole", back_populates="role")


class UserRole(Base, TimestampMixin):
    """Association table between users and roles."""
    __tablename__ = "user_roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("roles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Relationships
    role: Mapped["Role"] = relationship("Role", back_populates="users", lazy="joined")

    __table_args__ = (
        UniqueConstraint("user_id", "role_id", name="uq_user_roles_user_role"),
    )
