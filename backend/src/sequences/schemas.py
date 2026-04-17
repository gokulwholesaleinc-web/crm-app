"""Pydantic schemas for sales sequences."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class SequenceStepSchema(BaseModel):
    step_number: int
    type: str  # email, task, wait
    delay_days: int = 0
    template_id: int | None = None
    task_description: str | None = None


class SequenceCreate(BaseModel):
    name: str
    description: str | None = None
    steps: list[SequenceStepSchema] = []
    is_active: bool = True


class SequenceUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    steps: list[SequenceStepSchema] | None = None
    is_active: bool | None = None


class SequenceResponse(BaseModel):
    id: int
    name: str
    description: str | None = None
    steps: list[dict[str, Any]] = []
    is_active: bool
    created_by_id: int | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EnrollContactRequest(BaseModel):
    contact_id: int


class SequenceEnrollmentResponse(BaseModel):
    id: int
    sequence_id: int
    contact_id: int
    current_step: int
    status: str
    started_at: datetime
    next_step_at: datetime | None = None
    completed_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class ProcessDueResult(BaseModel):
    processed: int
    details: list[dict[str, Any]] = []
