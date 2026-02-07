"""Workflow automation API routes."""

from typing import Optional, List
from fastapi import APIRouter, Query
from src.core.constants import HTTPStatus
from src.core.router_utils import DBSession, CurrentUser, raise_not_found
from src.workflows.schemas import (
    WorkflowRuleCreate,
    WorkflowRuleUpdate,
    WorkflowRuleResponse,
    WorkflowExecutionResponse,
    WorkflowTestRequest,
)
from src.workflows.service import WorkflowService

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


@router.post("", response_model=WorkflowRuleResponse, status_code=HTTPStatus.CREATED)
async def create_workflow_rule(
    rule_data: WorkflowRuleCreate,
    current_user: CurrentUser,
    db: DBSession,
):
    """Create a new workflow rule."""
    service = WorkflowService(db)
    rule = await service.create_rule(rule_data, current_user.id)
    return WorkflowRuleResponse.model_validate(rule)


@router.get("", response_model=List[WorkflowRuleResponse])
async def list_workflow_rules(
    current_user: CurrentUser,
    db: DBSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    is_active: Optional[bool] = None,
    trigger_entity: Optional[str] = None,
):
    """List workflow rules."""
    service = WorkflowService(db)
    rules, _ = await service.get_list(
        page=page,
        page_size=page_size,
        is_active=is_active,
        trigger_entity=trigger_entity,
    )
    return [WorkflowRuleResponse.model_validate(r) for r in rules]


@router.get("/{rule_id}", response_model=WorkflowRuleResponse)
async def get_workflow_rule(
    rule_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Get a workflow rule by ID."""
    service = WorkflowService(db)
    rule = await service.get_by_id(rule_id)
    if not rule:
        raise_not_found("Workflow rule", rule_id)
    return WorkflowRuleResponse.model_validate(rule)


@router.put("/{rule_id}", response_model=WorkflowRuleResponse)
async def update_workflow_rule(
    rule_id: int,
    rule_data: WorkflowRuleUpdate,
    current_user: CurrentUser,
    db: DBSession,
):
    """Update a workflow rule."""
    service = WorkflowService(db)
    rule = await service.get_by_id(rule_id)
    if not rule:
        raise_not_found("Workflow rule", rule_id)
    updated = await service.update_rule(rule, rule_data)
    return WorkflowRuleResponse.model_validate(updated)


@router.delete("/{rule_id}", status_code=HTTPStatus.NO_CONTENT)
async def delete_workflow_rule(
    rule_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Delete a workflow rule."""
    service = WorkflowService(db)
    rule = await service.get_by_id(rule_id)
    if not rule:
        raise_not_found("Workflow rule", rule_id)
    await service.delete_rule(rule)


@router.get("/{rule_id}/executions", response_model=List[WorkflowExecutionResponse])
async def get_workflow_executions(
    rule_id: int,
    current_user: CurrentUser,
    db: DBSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """Get execution history for a workflow rule."""
    service = WorkflowService(db)
    rule = await service.get_by_id(rule_id)
    if not rule:
        raise_not_found("Workflow rule", rule_id)
    executions, _ = await service.get_executions(rule_id, page=page, page_size=page_size)
    return [WorkflowExecutionResponse.model_validate(e) for e in executions]


@router.post("/{rule_id}/test")
async def test_workflow_rule(
    rule_id: int,
    test_data: WorkflowTestRequest,
    current_user: CurrentUser,
    db: DBSession,
):
    """Dry-run a workflow rule against an entity."""
    service = WorkflowService(db)
    rule = await service.get_by_id(rule_id)
    if not rule:
        raise_not_found("Workflow rule", rule_id)

    # Build entity data from the entity_type and entity_id
    entity_data = await _get_entity_data(db, test_data.entity_type, test_data.entity_id)
    if entity_data is None:
        raise_not_found(test_data.entity_type.capitalize(), test_data.entity_id)

    results = await service.evaluate_rules(
        entity_type=test_data.entity_type,
        event=rule.trigger_event,
        entity_data=entity_data,
        entity_id=test_data.entity_id,
        dry_run=True,
    )

    return {"rule_id": rule_id, "dry_run": True, "results": results}


async def _get_entity_data(db, entity_type: str, entity_id: int) -> Optional[dict]:
    """Fetch entity data for workflow evaluation."""
    from sqlalchemy import select

    model_map = {}
    try:
        from src.leads.models import Lead
        model_map["lead"] = Lead
    except ImportError:
        pass
    try:
        from src.contacts.models import Contact
        model_map["contact"] = Contact
    except ImportError:
        pass
    try:
        from src.opportunities.models import Opportunity
        model_map["opportunity"] = Opportunity
    except ImportError:
        pass
    try:
        from src.activities.models import Activity
        model_map["activity"] = Activity
    except ImportError:
        pass

    model = model_map.get(entity_type)
    if not model:
        return None

    result = await db.execute(select(model).where(model.id == entity_id))
    entity = result.scalar_one_or_none()
    if not entity:
        return None

    # Convert to dict
    data = {}
    for col in entity.__table__.columns:
        val = getattr(entity, col.name, None)
        data[col.name] = val
    return data
