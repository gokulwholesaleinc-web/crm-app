"""Workflow automation service layer."""

from typing import Optional, List, Tuple, Dict, Any
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from src.workflows.models import WorkflowRule, WorkflowExecution
from src.workflows.schemas import WorkflowRuleCreate, WorkflowRuleUpdate
from src.core.base_service import BaseService
from src.core.constants import DEFAULT_PAGE_SIZE

# Supported operators for condition evaluation
OPERATORS = {
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    ">=": lambda a, b: a >= b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    "<": lambda a, b: a < b,
    "in": lambda a, b: a in b,
    "contains": lambda a, b: b in str(a) if a else False,
}


class WorkflowService(BaseService[WorkflowRule]):
    """Service for WorkflowRule CRUD and evaluation."""

    model = WorkflowRule

    async def get_list(
        self,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
        is_active: Optional[bool] = None,
        trigger_entity: Optional[str] = None,
    ) -> Tuple[List[WorkflowRule], int]:
        """Get paginated list of workflow rules."""
        query = select(WorkflowRule)

        if is_active is not None:
            query = query.where(WorkflowRule.is_active == is_active)

        if trigger_entity:
            query = query.where(WorkflowRule.trigger_entity == trigger_entity)

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar()

        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(WorkflowRule.created_at.desc())

        result = await self.db.execute(query)
        rules = list(result.scalars().all())

        return rules, total

    async def create_rule(self, data: WorkflowRuleCreate, user_id: int) -> WorkflowRule:
        """Create a new workflow rule."""
        rule = WorkflowRule(**data.model_dump(), created_by_id=user_id)
        self.db.add(rule)
        await self.db.flush()
        await self.db.refresh(rule)
        return rule

    async def update_rule(self, rule: WorkflowRule, data: WorkflowRuleUpdate) -> WorkflowRule:
        """Update a workflow rule."""
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(rule, field, value)
        await self.db.flush()
        await self.db.refresh(rule)
        return rule

    async def delete_rule(self, rule: WorkflowRule) -> None:
        """Delete a workflow rule."""
        await self.db.delete(rule)
        await self.db.flush()

    async def get_executions(
        self,
        rule_id: int,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> Tuple[List[WorkflowExecution], int]:
        """Get execution history for a rule."""
        query = select(WorkflowExecution).where(WorkflowExecution.rule_id == rule_id)

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar()

        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(WorkflowExecution.executed_at.desc())

        result = await self.db.execute(query)
        executions = list(result.scalars().all())

        return executions, total

    def _check_condition(self, entity_data: Dict[str, Any], condition: Dict[str, Any]) -> bool:
        """Check if a single condition matches the entity data."""
        field = condition.get("field")
        operator = condition.get("operator", "==")
        expected = condition.get("value")

        if not field or operator not in OPERATORS:
            return False

        actual = entity_data.get(field)
        if actual is None:
            return False

        try:
            # Convert types for comparison
            if isinstance(expected, (int, float)) and isinstance(actual, str):
                actual = type(expected)(actual)
            return OPERATORS[operator](actual, expected)
        except (ValueError, TypeError):
            return False

    async def evaluate_rules(
        self,
        entity_type: str,
        event: str,
        entity_data: Dict[str, Any],
        entity_id: int,
        dry_run: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Evaluate all active rules against an entity event.

        Returns list of results for each matching rule.
        """
        # Get active rules matching the trigger
        result = await self.db.execute(
            select(WorkflowRule)
            .where(WorkflowRule.is_active == True)
            .where(WorkflowRule.trigger_entity == entity_type)
            .where(WorkflowRule.trigger_event == event)
        )
        rules = list(result.scalars().all())

        results = []
        for rule in rules:
            # Check conditions
            conditions_met = True
            if rule.conditions:
                conditions_met = self._check_condition(entity_data, rule.conditions)

            if not conditions_met:
                status = "skipped"
                result_data = {"reason": "Conditions not met"}
            else:
                status = "success"
                result_data = {
                    "matched_actions": rule.actions or [],
                    "conditions_met": True,
                }

            if not dry_run:
                execution = WorkflowExecution(
                    rule_id=rule.id,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    status=status,
                    result=result_data,
                )
                self.db.add(execution)

            results.append({
                "rule_id": rule.id,
                "rule_name": rule.name,
                "status": status,
                "result": result_data,
            })

        if not dry_run:
            await self.db.flush()

        return results
