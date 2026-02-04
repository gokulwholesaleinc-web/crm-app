"""Pydantic schemas for activities."""

from datetime import datetime, date
from typing import Optional, List
from pydantic import BaseModel, ConfigDict


class ActivityBase(BaseModel):
    activity_type: str
    subject: str
    description: Optional[str] = None
    entity_type: str
    entity_id: int
    scheduled_at: Optional[datetime] = None
    due_date: Optional[date] = None
    priority: str = "normal"
    owner_id: Optional[int] = None
    assigned_to_id: Optional[int] = None


class ActivityCreate(ActivityBase):
    # Call-specific
    call_duration_minutes: Optional[int] = None
    call_outcome: Optional[str] = None
    # Email-specific
    email_to: Optional[str] = None
    email_cc: Optional[str] = None
    # Meeting-specific
    meeting_location: Optional[str] = None
    meeting_attendees: Optional[str] = None
    # Task-specific
    task_reminder_at: Optional[datetime] = None


class ActivityUpdate(BaseModel):
    subject: Optional[str] = None
    description: Optional[str] = None
    scheduled_at: Optional[datetime] = None
    due_date: Optional[date] = None
    priority: Optional[str] = None
    is_completed: Optional[bool] = None
    completed_at: Optional[datetime] = None
    owner_id: Optional[int] = None
    assigned_to_id: Optional[int] = None
    # Call-specific
    call_duration_minutes: Optional[int] = None
    call_outcome: Optional[str] = None
    # Email-specific
    email_to: Optional[str] = None
    email_cc: Optional[str] = None
    email_opened: Optional[bool] = None
    # Meeting-specific
    meeting_location: Optional[str] = None
    meeting_attendees: Optional[str] = None
    # Task-specific
    task_reminder_at: Optional[datetime] = None


class ActivityResponse(ActivityBase):
    id: int
    is_completed: bool
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    # Call-specific
    call_duration_minutes: Optional[int] = None
    call_outcome: Optional[str] = None
    # Email-specific
    email_to: Optional[str] = None
    email_cc: Optional[str] = None
    email_opened: Optional[bool] = None
    # Meeting-specific
    meeting_location: Optional[str] = None
    meeting_attendees: Optional[str] = None
    # Task-specific
    task_reminder_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ActivityListResponse(BaseModel):
    items: List[ActivityResponse]
    total: int
    page: int
    page_size: int
    pages: int


class TimelineItem(BaseModel):
    id: int
    activity_type: str
    subject: str
    description: Optional[str]
    entity_type: str
    entity_id: int
    scheduled_at: Optional[str]
    due_date: Optional[str]
    completed_at: Optional[str]
    is_completed: bool
    priority: str
    created_at: str
    owner_id: Optional[int]
    assigned_to_id: Optional[int]
    call_duration_minutes: Optional[int]
    call_outcome: Optional[str]
    meeting_location: Optional[str]


class TimelineResponse(BaseModel):
    items: List[TimelineItem]


class CompleteActivityRequest(BaseModel):
    notes: Optional[str] = None
