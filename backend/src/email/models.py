"""Email queue model for tracking sent emails."""

from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, ForeignKey, Text, Boolean, DateTime, func, Index
from sqlalchemy.orm import Mapped, mapped_column
from src.database import Base


class EmailQueue(Base):
    """Email queue model - tracks all outbound emails with open/click tracking."""
    __tablename__ = "email_queue"

    id: Mapped[int] = mapped_column(primary_key=True)
    to_email: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)

    # Status tracking
    status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False
    )  # pending, sent, failed
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    sent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Open/Click tracking
    opened_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    clicked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    open_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    click_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Entity link (polymorphic)
    entity_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    entity_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Template / Campaign references
    template_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("email_templates.id", ondelete="SET NULL"), nullable=True
    )
    campaign_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True
    )

    # Who sent it
    sent_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        Index("ix_email_queue_entity", "entity_type", "entity_id"),
        Index("ix_email_queue_status", "status"),
        Index("ix_email_queue_sent_by", "sent_by_id"),
    )
