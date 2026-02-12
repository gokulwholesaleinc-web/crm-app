"""White-label/multi-tenant models."""

from typing import Optional
from sqlalchemy import String, Integer, ForeignKey, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.database import Base
from src.core.mixins.auditable import TimestampMixin


class Tenant(Base, TimestampMixin):
    """
    Tenant model for multi-tenant white-label support.

    Each tenant represents a separate organization using the CRM
    with their own branding and configuration.
    """
    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Identification
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    domain: Mapped[Optional[str]] = mapped_column(String(255), unique=True, index=True)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Subscription/Plan
    plan: Mapped[str] = mapped_column(String(50), default="starter")  # starter, professional, enterprise
    max_users: Mapped[int] = mapped_column(Integer, default=5)
    max_contacts: Mapped[Optional[int]] = mapped_column(Integer)

    # Relationships
    settings: Mapped["TenantSettings"] = relationship(
        "TenantSettings",
        back_populates="tenant",
        uselist=False,
        lazy="joined",
        cascade="all, delete-orphan",
    )


class TenantSettings(Base, TimestampMixin):
    """
    Tenant-specific settings for white-label customization.

    Includes branding, theme colors, feature flags, etc.
    """
    __tablename__ = "tenant_settings"

    id: Mapped[int] = mapped_column(primary_key=True)

    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )

    # Branding
    company_name: Mapped[Optional[str]] = mapped_column(String(255))
    logo_url: Mapped[Optional[str]] = mapped_column(String(500))
    favicon_url: Mapped[Optional[str]] = mapped_column(String(500))

    # Theme colors
    primary_color: Mapped[str] = mapped_column(String(7), default="#6366f1")
    secondary_color: Mapped[str] = mapped_column(String(7), default="#8b5cf6")
    accent_color: Mapped[str] = mapped_column(String(7), default="#22c55e")

    # Email settings
    email_from_name: Mapped[Optional[str]] = mapped_column(String(255))
    email_from_address: Mapped[Optional[str]] = mapped_column(String(255))

    # Feature flags (JSON string)
    feature_flags: Mapped[Optional[str]] = mapped_column(Text)  # {"ai_enabled": true, "campaigns": true}

    # Custom CSS (for advanced customization)
    custom_css: Mapped[Optional[str]] = mapped_column(Text)

    # Footer/Legal
    footer_text: Mapped[Optional[str]] = mapped_column(String(500))
    privacy_policy_url: Mapped[Optional[str]] = mapped_column(String(500))
    terms_of_service_url: Mapped[Optional[str]] = mapped_column(String(500))

    # Localization
    default_language: Mapped[str] = mapped_column(String(5), default="en")
    default_timezone: Mapped[str] = mapped_column(String(50), default="UTC")
    default_currency: Mapped[str] = mapped_column(String(3), default="USD")
    date_format: Mapped[str] = mapped_column(String(20), default="MM/DD/YYYY")

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="settings")


class TenantUser(Base, TimestampMixin):
    """Junction table linking users to tenants."""
    __tablename__ = "tenant_users"

    id: Mapped[int] = mapped_column(primary_key=True)

    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Role within tenant
    role: Mapped[str] = mapped_column(String(50), default="member")  # admin, manager, member

    # Is this the user's primary/default tenant?
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
