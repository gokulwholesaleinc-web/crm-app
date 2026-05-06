"""Activity model for unified activity tracking."""

import enum
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.core.mixins.auditable import AuditableMixin
from src.database import Base


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
    description: Mapped[str | None] = mapped_column(Text)

    # Dynamic link to any entity (polymorphic)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)  # contacts, leads, opportunities, companies
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False)

    # Cross-reference contact: when entity_type='opportunities', the
    # service copies Opportunity.contact_id here so the contact's
    # Activities tab can surface opportunity-driven rows without
    # double-writing.
    contact_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("contacts.id", ondelete="SET NULL"),
        index=True,
    )

    # Scheduling
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    due_date: Mapped[date | None] = mapped_column(Date)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Status
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    priority: Mapped[str] = mapped_column(String(20), default="normal")  # low, normal, high, urgent

    # Call-specific fields
    call_duration_minutes: Mapped[int | None] = mapped_column(Integer)
    call_outcome: Mapped[str | None] = mapped_column(String(50))  # connected, voicemail, no_answer, busy

    # Email-specific fields
    email_to: Mapped[str | None] = mapped_column(String(500))
    email_cc: Mapped[str | None] = mapped_column(String(500))
    email_opened: Mapped[bool | None] = mapped_column(Boolean)

    # Meeting-specific fields
    meeting_location: Mapped[str | None] = mapped_column(String(255))
    meeting_attendees: Mapped[str | None] = mapped_column(Text)  # JSON array of attendee info

    # Task-specific fields
    task_reminder_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Owner/assignee
    owner_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )
    assigned_to_id: Mapped[int | None] = mapped_column(
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
