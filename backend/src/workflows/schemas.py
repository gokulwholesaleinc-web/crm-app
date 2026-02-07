"""Pydantic schemas for workflows."""

from datetime import datetime
from typing import Optional, List, Any, Dict
from pydantic import BaseModel, ConfigDict


class WorkflowRuleCreate(BaseModel):
    name: str
    description: Optional[str] = None
    is_active: bool = True
    trigger_entity: str
    trigger_event: str
    conditions: Optional[Dict[str, Any]] = None
    actions: Optional[List[Dict[str, Any]]] = None


class WorkflowRuleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    trigger_entity: Optional[str] = None
    trigger_event: Optional[str] = None
    conditions: Optional[Dict[str, Any]] = None
    actions: Optional[List[Dict[str, Any]]] = None


class WorkflowRuleResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    is_active: bool
    trigger_entity: str
    trigger_event: str
    conditions: Optional[Dict[str, Any]] = None
    actions: Optional[List[Dict[str, Any]]] = None
    created_by_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WorkflowExecutionResponse(BaseModel):
    id: int
    rule_id: int
    entity_type: str
    entity_id: int
    status: str
    result: Optional[Dict[str, Any]] = None
    executed_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WorkflowTestRequest(BaseModel):
    entity_type: str
    entity_id: int
