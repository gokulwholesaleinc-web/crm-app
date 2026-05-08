"""Lead auto-assignment service layer."""

import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select

from src.assignment.models import AssignmentLog, AssignmentRule
from src.assignment.schemas import AssignmentRuleCreate, AssignmentRuleUpdate
from src.core.base_service import BaseService
from src.core.constants import DEFAULT_PAGE_SIZE
from src.leads.models import Lead

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AssignmentDecision:
    """Result of an assign_lead call.

    `reason` is one of:
      - `rule_match` — a filtered rule's filters matched the lead.
      - `default_fallback` — no filtered rule matched; the catch-all
        `is_default=True` rule fired.
    `manual_override` is reserved for log rows that callers write
    directly (e.g. an admin reassign action) and never produced here.
    """
    user_id: int
    rule_id: int
    reason: str


class AssignmentService(BaseService[AssignmentRule]):
    """Service for AssignmentRule CRUD and lead assignment logic."""

    model = AssignmentRule

    async def get_list(
        self,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
        is_active: bool | None = None,
    ) -> tuple[list[AssignmentRule], int]:
        """Get paginated list of assignment rules."""
        query = select(AssignmentRule)

        if is_active is not None:
            query = query.where(AssignmentRule.is_active == is_active)

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(AssignmentRule.created_at.desc())

        result = await self.db.execute(query)
        rules = list(result.scalars().all())
        return rules, total

    async def create_rule(self, data: AssignmentRuleCreate, user_id: int) -> AssignmentRule:
        rule = AssignmentRule(**data.model_dump(), created_by_id=user_id)
        self.db.add(rule)
        await self.db.flush()
        await self.db.refresh(rule)
        return rule

    async def update_rule(self, rule: AssignmentRule, data: AssignmentRuleUpdate) -> AssignmentRule:
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(rule, field, value)
        await self.db.flush()
        await self.db.refresh(rule)
        return rule

    async def delete_rule(self, rule: AssignmentRule) -> None:
        await self.db.delete(rule)
        await self.db.flush()

    def _matches_filters(self, lead_data: dict[str, Any], filters: dict[str, Any] | None) -> bool:
        """Check if a lead matches the rule's filters."""
        if not filters:
            return True

        # Check source filter
        if "source" in filters:
            lead_source = lead_data.get("source_name") or lead_data.get("source")
            if lead_source != filters["source"]:
                return False

        # Check source_id filter
        if "source_id" in filters:
            if lead_data.get("source_id") != filters["source_id"]:
                return False

        # Check industry filter
        if "industry" in filters:
            if lead_data.get("industry") != filters["industry"]:
                return False

        # Check status filter
        if "status" in filters:
            if lead_data.get("status") != filters["status"]:
                return False

        return True

    async def _get_round_robin_user(self, rule: AssignmentRule) -> int | None:
        """Get next user in round-robin rotation."""
        if not rule.user_ids:
            return None
        next_index = (rule.last_assigned_index + 1) % len(rule.user_ids)
        user_id = rule.user_ids[next_index]
        rule.last_assigned_index = next_index
        await self.db.flush()
        return user_id

    async def _get_load_balance_user(self, rule: AssignmentRule) -> int | None:
        """Get user with fewest active leads."""
        if not rule.user_ids:
            return None

        # Count active leads per user
        user_lead_counts = {}
        for user_id in rule.user_ids:
            result = await self.db.execute(
                select(func.count()).select_from(Lead).where(
                    Lead.owner_id == user_id,
                    Lead.status.in_(["new", "contacted", "qualified"]),
                )
            )
            user_lead_counts[user_id] = result.scalar() or 0

        # Return user with fewest leads
        return min(user_lead_counts, key=lambda u: user_lead_counts[u])

    async def _resolve_user(self, rule: AssignmentRule) -> int | None:
        if rule.assignment_type == "round_robin":
            return await self._get_round_robin_user(rule)
        if rule.assignment_type == "load_balance":
            return await self._get_load_balance_user(rule)
        return None

    async def assign_lead(self, lead_data: dict[str, Any]) -> AssignmentDecision | None:
        """Pick an assignee for a new lead per the active rule set.

        Two-pass selection so a default catch-all never starves a
        filtered rule:
          1. Iterate non-default active rules in creation order; first
             whose `filters` match wins.
          2. If no filtered rule matched, the active `is_default=True`
             rule (at most one — DB partial unique index enforces) fires
             as the fallback.

        Returns `None` when no rule produces a user — the caller should
        leave `owner_id` unset rather than guess.
        """
        result = await self.db.execute(
            select(AssignmentRule)
            .where(AssignmentRule.is_active == True)
            .order_by(AssignmentRule.created_at.asc())
        )
        rules = list(result.scalars().all())

        # Pass 1: filtered (non-default) rules in creation order.
        for rule in rules:
            if rule.is_default:
                continue
            if not self._matches_filters(lead_data, rule.filters):
                continue
            user_id = await self._resolve_user(rule)
            if user_id is not None:
                return AssignmentDecision(
                    user_id=user_id, rule_id=rule.id, reason="rule_match",
                )

        # Pass 2: default fallback. Partial unique index → at most one.
        for rule in rules:
            if not rule.is_default:
                continue
            user_id = await self._resolve_user(rule)
            if user_id is not None:
                return AssignmentDecision(
                    user_id=user_id, rule_id=rule.id, reason="default_fallback",
                )
            break

        return None

    async def log_decision(
        self,
        lead_id: int,
        decision: AssignmentDecision,
    ) -> AssignmentLog:
        """Persist an audit row for an auto-assignment decision."""
        log = AssignmentLog(
            lead_id=lead_id,
            rule_id=decision.rule_id,
            assigned_user_id=decision.user_id,
            reason=decision.reason,
        )
        self.db.add(log)
        await self.db.flush()
        return log

    async def log_manual_override(
        self,
        lead_id: int,
        user_id: int | None,
    ) -> AssignmentLog:
        """Audit row for an admin/owner reassign action.

        Keeps the per-rule load-balance math honest — the lead now
        sits with `user_id`, but no rule "earned" the placement.
        """
        log = AssignmentLog(
            lead_id=lead_id,
            rule_id=None,
            assigned_user_id=user_id,
            reason="manual_override",
        )
        self.db.add(log)
        await self.db.flush()
        return log

    async def get_assignment_stats(self, user_ids: list[int]) -> list[dict[str, Any]]:
        """Get active lead counts for a list of users."""
        stats = []
        for user_id in user_ids:
            result = await self.db.execute(
                select(func.count()).select_from(Lead).where(
                    Lead.owner_id == user_id,
                    Lead.status.in_(["new", "contacted", "qualified"]),
                )
            )
            count = result.scalar() or 0
            stats.append({"user_id": user_id, "active_leads_count": count})
        return stats
