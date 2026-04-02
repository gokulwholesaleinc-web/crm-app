"""Google Calendar integration models."""

from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, ForeignKey, Text, DateTime, Boolean, func, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from src.database import Base


class GoogleCalendarCredential(Base):
    """Stores OAuth2 credentials for Google Calendar per user."""
    __tablename__ = "google_calendar_credentials"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    token_expiry: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    calendar_id: Mapped[str] = mapped_column(String(255), default="primary")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class CalendarSyncEvent(Base):
    """Maps CRM activities to Google Calendar events for two-way sync."""
    __tablename__ = "calendar_sync_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    activity_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("activities.id", ondelete="SET NULL"),
        nullable=True,
    )
    google_event_id: Mapped[str] = mapped_column(String(255), nullable=False)
    google_calendar_id: Mapped[str] = mapped_column(String(255), default="primary")
    sync_direction: Mapped[str] = mapped_column(String(20), nullable=False)  # crm_to_google, google_to_crm
    last_synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "google_event_id", name="uq_calendar_sync_user_event"),
    )
