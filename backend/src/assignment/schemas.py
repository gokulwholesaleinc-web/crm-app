"""Pydantic schemas for assignment rules."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class AssignmentRuleCreate(BaseModel):
    name: str
    assignment_type: str  # round_robin or load_balance
    user_ids: list[int]
    filters: dict[str, Any] | None = None
    is_active: bool = True


class AssignmentRuleUpdate(BaseModel):
    name: str | None = None
    assignment_type: str | None = None
    user_ids: list[int] | None = None
    filters: dict[str, Any] | None = None
    is_active: bool | None = None


class AssignmentRuleResponse(BaseModel):
    id: int
    name: str
    assignment_type: str
    user_ids: list[int]
    filters: dict[str, Any] | None = None
    last_assigned_index: int
    is_active: bool
    created_by_id: int | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AssignmentStatsResponse(BaseModel):
    user_id: int
    active_leads_count: int
