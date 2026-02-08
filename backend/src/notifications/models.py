"""Notification model for in-app notifications."""

from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, ForeignKey, Text, DateTime, Boolean, func, Index
from sqlalchemy.orm import Mapped, mapped_column
from src.database import Base


class Notification(Base):
    """In-app notification for users."""
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Target user
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    # Notification content
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)

    # Entity link (polymorphic)
    entity_type: Mapped[Optional[str]] = mapped_column(String(50))
    entity_id: Mapped[Optional[int]] = mapped_column(Integer)

    # State
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_notifications_user_read", "user_id", "is_read"),
        Index("ix_notifications_entity", "entity_type", "entity_id"),
    )
