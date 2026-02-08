"""Pydantic schemas for sales sequences."""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict


class SequenceStepSchema(BaseModel):
    step_number: int
    type: str  # email, task, wait
    delay_days: int = 0
    template_id: Optional[int] = None
    task_description: Optional[str] = None


class SequenceCreate(BaseModel):
    name: str
    description: Optional[str] = None
    steps: List[SequenceStepSchema] = []
    is_active: bool = True


class SequenceUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    steps: Optional[List[SequenceStepSchema]] = None
    is_active: Optional[bool] = None


class SequenceResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    steps: List[Dict[str, Any]] = []
    is_active: bool
    created_by_id: Optional[int] = None
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
    next_step_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ProcessDueResult(BaseModel):
    processed: int
    details: List[Dict[str, Any]] = []
