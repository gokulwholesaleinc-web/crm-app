"""Webhook models for external integrations."""

from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, ForeignKey, Text, Boolean, DateTime, func, JSON
from sqlalchemy.orm import Mapped, mapped_column
from src.database import Base


class Webhook(Base):
    """Webhook configuration for sending events to external URLs."""
    __tablename__ = "webhooks"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(String(2000), nullable=False)
    events: Mapped[list] = mapped_column(JSON, nullable=False)  # List of event type strings
    secret: Mapped[Optional[str]] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_by_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class WebhookDelivery(Base):
    """Record of a webhook delivery attempt."""
    __tablename__ = "webhook_deliveries"

    id: Mapped[int] = mapped_column(primary_key=True)

    webhook_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("webhooks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[Optional[dict]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # success, failed
    response_code: Mapped[Optional[int]] = mapped_column(Integer)
    error: Mapped[Optional[str]] = mapped_column(Text)

    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
