"""Email models for tracking sent and received emails."""

from datetime import date, datetime
from typing import Optional
from sqlalchemy import String, Integer, ForeignKey, Text, Boolean, DateTime, Date, func, Index, JSON
from sqlalchemy.orm import Mapped, mapped_column
from src.database import Base


class EmailQueue(Base):
    """Email queue model - tracks all outbound emails with open/click tracking."""
    __tablename__ = "email_queue"

    id: Mapped[int] = mapped_column(primary_key=True)
    to_email: Mapped[str] = mapped_column(String(255), nullable=False)
    from_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    cc: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    bcc: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Status tracking
    status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False
    )  # pending, sent, failed, retry
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    next_retry_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
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

    # Provider routing + threading (populated when sent_via='gmail')
    sent_via: Mapped[str] = mapped_column(
        String(20), default="resend", server_default="resend", nullable=False
    )
    message_id: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    thread_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    __table_args__ = (
        Index("ix_email_queue_entity", "entity_type", "entity_id"),
        Index("ix_email_queue_status", "status"),
        Index("ix_email_queue_sent_by", "sent_by_id"),
        Index("ix_email_queue_thread_id", "thread_id"),
    )


class EmailSettings(Base):
    """Email sending settings - daily limits and warmup configuration."""
    __tablename__ = "email_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    daily_send_limit: Mapped[int] = mapped_column(Integer, default=200, nullable=False)
    warmup_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    warmup_start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    warmup_target_daily: Mapped[int] = mapped_column(Integer, default=200, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class InboundEmail(Base):
    """Inbound email model - stores emails received via Resend webhook."""
    __tablename__ = "inbound_emails"

    id: Mapped[int] = mapped_column(primary_key=True)
    resend_email_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    from_email: Mapped[str] = mapped_column(String(255), nullable=False)
    to_email: Mapped[str] = mapped_column(String(255), nullable=False)
    cc: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    bcc: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    body_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    body_html: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Threading
    message_id: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    in_reply_to: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Attachments metadata
    attachments: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Entity link (polymorphic - auto-matched to contact)
    entity_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    entity_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Timestamps
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_inbound_emails_entity", "entity_type", "entity_id"),
        Index("ix_inbound_emails_from", "from_email"),
    )
