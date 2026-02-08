"""Assignment rule API routes."""

from typing import Optional, List
from fastapi import APIRouter, Query
from src.core.constants import HTTPStatus
from src.core.router_utils import DBSession, CurrentUser, raise_not_found
from src.assignment.schemas import (
    AssignmentRuleCreate,
    AssignmentRuleUpdate,
    AssignmentRuleResponse,
    AssignmentStatsResponse,
)
from src.assignment.service import AssignmentService

router = APIRouter(prefix="/api/assignment-rules", tags=["assignment"])


@router.post("", response_model=AssignmentRuleResponse, status_code=HTTPStatus.CREATED)
async def create_rule(
    data: AssignmentRuleCreate,
    current_user: CurrentUser,
    db: DBSession,
):
    """Create a new assignment rule."""
    service = AssignmentService(db)
    rule = await service.create_rule(data, current_user.id)
    return AssignmentRuleResponse.model_validate(rule)


@router.get("", response_model=List[AssignmentRuleResponse])
async def list_rules(
    current_user: CurrentUser,
    db: DBSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    is_active: Optional[bool] = None,
):
    """List assignment rules."""
    service = AssignmentService(db)
    rules, _ = await service.get_list(page=page, page_size=page_size, is_active=is_active)
    return [AssignmentRuleResponse.model_validate(r) for r in rules]


@router.get("/{rule_id}", response_model=AssignmentRuleResponse)
async def get_rule(
    rule_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Get an assignment rule by ID."""
    service = AssignmentService(db)
    rule = await service.get_by_id(rule_id)
    if not rule:
        raise_not_found("Assignment rule", rule_id)
    return AssignmentRuleResponse.model_validate(rule)


@router.put("/{rule_id}", response_model=AssignmentRuleResponse)
async def update_rule(
    rule_id: int,
    data: AssignmentRuleUpdate,
    current_user: CurrentUser,
    db: DBSession,
):
    """Update an assignment rule."""
    service = AssignmentService(db)
    rule = await service.get_by_id(rule_id)
    if not rule:
        raise_not_found("Assignment rule", rule_id)
    updated = await service.update_rule(rule, data)
    return AssignmentRuleResponse.model_validate(updated)


@router.delete("/{rule_id}", status_code=HTTPStatus.NO_CONTENT)
async def delete_rule(
    rule_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Delete an assignment rule."""
    service = AssignmentService(db)
    rule = await service.get_by_id(rule_id)
    if not rule:
        raise_not_found("Assignment rule", rule_id)
    await service.delete_rule(rule)


@router.get("/{rule_id}/stats", response_model=List[AssignmentStatsResponse])
async def get_stats(
    rule_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Get assignment statistics for a rule's team members."""
    service = AssignmentService(db)
    rule = await service.get_by_id(rule_id)
    if not rule:
        raise_not_found("Assignment rule", rule_id)
    stats = await service.get_assignment_stats(rule.user_ids or [])
    return [AssignmentStatsResponse(**s) for s in stats]
