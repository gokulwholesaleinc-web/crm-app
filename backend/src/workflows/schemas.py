"""Pydantic schemas for workflows."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class WorkflowRuleCreate(BaseModel):
    name: str
    description: str | None = None
    is_active: bool = True
    trigger_entity: str
    trigger_event: str
    conditions: dict[str, Any] | None = None
    actions: list[dict[str, Any]] | None = None


class WorkflowRuleUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    is_active: bool | None = None
    trigger_entity: str | None = None
    trigger_event: str | None = None
    conditions: dict[str, Any] | None = None
    actions: list[dict[str, Any]] | None = None


class WorkflowRuleResponse(BaseModel):
    id: int
    name: str
    description: str | None = None
    is_active: bool
    trigger_entity: str
    trigger_event: str
    conditions: dict[str, Any] | None = None
    actions: list[dict[str, Any]] | None = None
    created_by_id: int | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WorkflowExecutionResponse(BaseModel):
    id: int
    rule_id: int
    entity_type: str
    entity_id: int
    status: str
    result: dict[str, Any] | None = None
    executed_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WorkflowTestRequest(BaseModel):
    entity_type: str
    entity_id: int
