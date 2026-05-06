"""Pydantic schemas for activities."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class ActivityBase(BaseModel):
    activity_type: str
    subject: str
    description: str | None = None
    entity_type: str
    entity_id: int
    scheduled_at: datetime | None = None
    due_date: date | None = None
    priority: str = "normal"
    owner_id: int | None = None
    assigned_to_id: int | None = None


class ActivityCreate(ActivityBase):
    entity_type: str | None = None
    entity_id: int | None = None
    contact_id: int | None = None

    # Call-specific
    call_duration_minutes: int | None = None
    call_outcome: str | None = None
    # Email-specific
    email_to: str | None = None
    email_cc: str | None = None
    # Meeting-specific
    meeting_location: str | None = None
    meeting_attendees: str | None = None
    # Task-specific
    task_reminder_at: datetime | None = None


class ActivityUpdate(BaseModel):
    subject: str | None = None
    description: str | None = None
    scheduled_at: datetime | None = None
    due_date: date | None = None
    priority: str | None = None
    is_completed: bool | None = None
    completed_at: datetime | None = None
    owner_id: int | None = None
    assigned_to_id: int | None = None
    # Call-specific
    call_duration_minutes: int | None = None
    call_outcome: str | None = None
    # Email-specific
    email_to: str | None = None
    email_cc: str | None = None
    email_opened: bool | None = None
    # Meeting-specific
    meeting_location: str | None = None
    meeting_attendees: str | None = None
    # Task-specific
    task_reminder_at: datetime | None = None


class ActivityResponse(ActivityBase):
    id: int
    is_completed: bool
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    contact_id: int | None = None
    # Call-specific
    call_duration_minutes: int | None = None
    call_outcome: str | None = None
    # Email-specific
    email_to: str | None = None
    email_cc: str | None = None
    email_opened: bool | None = None
    # Meeting-specific
    meeting_location: str | None = None
    meeting_attendees: str | None = None
    # Task-specific
    task_reminder_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class ActivityListResponse(BaseModel):
    items: list[ActivityResponse]
    total: int
    page: int
    page_size: int
    pages: int


class TimelineItem(BaseModel):
    id: int
    activity_type: str
    subject: str
    description: str | None
    entity_type: str
    entity_id: int
    scheduled_at: str | None
    due_date: str | None
    completed_at: str | None
    is_completed: bool
    priority: str
    created_at: str
    owner_id: int | None
    assigned_to_id: int | None
    call_duration_minutes: int | None
    call_outcome: str | None
    meeting_location: str | None


class TimelineResponse(BaseModel):
    items: list[TimelineItem]


class UnifiedTimelineEvent(BaseModel):
    """A single event in the unified timeline (activity, email, or sequence step)."""
    id: int
    event_type: str  # activity, email_sent, email_opened, email_clicked, sequence_step
    subject: str
    description: str | None = None
    entity_type: str | None = None
    entity_id: int | None = None
    timestamp: str
    metadata: dict | None = None


class UnifiedTimelineResponse(BaseModel):
    items: list[UnifiedTimelineEvent]


class CompleteActivityRequest(BaseModel):
    notes: str | None = None
