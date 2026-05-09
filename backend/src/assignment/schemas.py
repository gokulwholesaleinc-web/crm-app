"""Pydantic schemas for assignment rules."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class AssignmentRuleCreate(BaseModel):
    name: str
    assignment_type: Literal["round_robin", "load_balance"]
    user_ids: list[int]
    filters: dict[str, Any] | None = None
    is_active: bool = True
    is_default: bool = False


class AssignmentRuleUpdate(BaseModel):
    name: str | None = None
    assignment_type: Literal["round_robin", "load_balance"] | None = None
    user_ids: list[int] | None = None
    filters: dict[str, Any] | None = None
    is_active: bool | None = None
    is_default: bool | None = None


class AssignmentRuleResponse(BaseModel):
    id: int
    name: str
    assignment_type: str
    user_ids: list[int]
    filters: dict[str, Any] | None = None
    last_assigned_index: int
    is_active: bool
    is_default: bool
    created_by_id: int | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AssignmentStatsResponse(BaseModel):
    user_id: int
    active_leads_count: int


class AssignmentLogResponse(BaseModel):
    id: int
    lead_id: int
    rule_id: int | None
    assigned_user_id: int | None
    reason: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
