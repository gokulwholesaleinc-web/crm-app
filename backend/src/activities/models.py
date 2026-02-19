"""Activity model for unified activity tracking."""

from datetime import datetime, date
from typing import Optional
from sqlalchemy import String, Integer, ForeignKey, Text, DateTime, Date, Boolean, Index
from sqlalchemy.orm import Mapped, mapped_column
from src.database import Base
from src.core.mixins.auditable import AuditableMixin
import enum


class ActivityType(str, enum.Enum):
    CALL = "call"
    EMAIL = "email"
    MEETING = "meeting"
    TASK = "task"
    NOTE = "note"


class Activity(Base, AuditableMixin):
    """
    Unified activity model with dynamic links to any entity.

    Follows ERPNext's dynamic link pattern - one activity table
    can link to contacts, leads, opportunities, companies, etc.
    """
    __tablename__ = "activities"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Activity type
    activity_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)

    # Content
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)

    # Dynamic link to any entity (polymorphic)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)  # contacts, leads, opportunities, companies
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False)

    # Scheduling
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    due_date: Mapped[Optional[date]] = mapped_column(Date)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Status
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    priority: Mapped[str] = mapped_column(String(20), default="normal")  # low, normal, high, urgent

    # Call-specific fields
    call_duration_minutes: Mapped[Optional[int]] = mapped_column(Integer)
    call_outcome: Mapped[Optional[str]] = mapped_column(String(50))  # connected, voicemail, no_answer, busy

    # Email-specific fields
    email_to: Mapped[Optional[str]] = mapped_column(String(500))
    email_cc: Mapped[Optional[str]] = mapped_column(String(500))
    email_opened: Mapped[Optional[bool]] = mapped_column(Boolean)

    # Meeting-specific fields
    meeting_location: Mapped[Optional[str]] = mapped_column(String(255))
    meeting_attendees: Mapped[Optional[str]] = mapped_column(Text)  # JSON array of attendee info

    # Task-specific fields
    task_reminder_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Owner/assignee
    owner_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )
    assigned_to_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )

    __table_args__ = (
        Index("ix_activities_entity", "entity_type", "entity_id"),
        Index("ix_activities_scheduled", "scheduled_at"),
        Index("ix_activities_due", "due_date"),
        Index("ix_activities_owner_created", "owner_id", "created_at"),
    )
