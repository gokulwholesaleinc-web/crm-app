"""Pydantic schemas for assignment rules."""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict


class AssignmentRuleCreate(BaseModel):
    name: str
    assignment_type: str  # round_robin or load_balance
    user_ids: List[int]
    filters: Optional[Dict[str, Any]] = None
    is_active: bool = True


class AssignmentRuleUpdate(BaseModel):
    name: Optional[str] = None
    assignment_type: Optional[str] = None
    user_ids: Optional[List[int]] = None
    filters: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class AssignmentRuleResponse(BaseModel):
    id: int
    name: str
    assignment_type: str
    user_ids: List[int]
    filters: Optional[Dict[str, Any]] = None
    last_assigned_index: int
    is_active: bool
    created_by_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AssignmentStatsResponse(BaseModel):
    user_id: int
    active_leads_count: int
