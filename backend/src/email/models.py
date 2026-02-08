"""Email queue model for tracking sent emails."""

from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, ForeignKey, Text, DateTime, func, Index
from sqlalchemy.orm import Mapped, mapped_column
from src.database import Base


class EmailQueue(Base):
    """Tracks queued and sent emails with open/click tracking."""
    __tablename__ = "email_queue"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Recipient
    to_email: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)

    # Status: pending, sent, failed
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[Optional[str]] = mapped_column(Text)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Tracking
    opened_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    clicked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    open_count: Mapped[int] = mapped_column(Integer, default=0)
    click_count: Mapped[int] = mapped_column(Integer, default=0)

    # Entity link (polymorphic)
    entity_type: Mapped[Optional[str]] = mapped_column(String(50))
    entity_id: Mapped[Optional[int]] = mapped_column(Integer)

    # References
    template_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("email_templates.id", ondelete="SET NULL")
    )
    campaign_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("campaigns.id", ondelete="SET NULL")
    )
    sent_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL")
    )

    __table_args__ = (
        Index("ix_email_queue_entity", "entity_type", "entity_id"),
        Index("ix_email_queue_status", "status"),
    )
