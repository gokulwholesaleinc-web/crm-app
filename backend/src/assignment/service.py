"""Lead auto-assignment service layer."""

import logging
from typing import Optional, List, Tuple, Dict, Any

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.assignment.models import AssignmentRule
from src.assignment.schemas import AssignmentRuleCreate, AssignmentRuleUpdate
from src.leads.models import Lead
from src.core.base_service import BaseService
from src.core.constants import DEFAULT_PAGE_SIZE

logger = logging.getLogger(__name__)


class AssignmentService(BaseService[AssignmentRule]):
    """Service for AssignmentRule CRUD and lead assignment logic."""

    model = AssignmentRule

    async def get_list(
        self,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
        is_active: Optional[bool] = None,
    ) -> Tuple[List[AssignmentRule], int]:
        """Get paginated list of assignment rules."""
        query = select(AssignmentRule)

        if is_active is not None:
            query = query.where(AssignmentRule.is_active == is_active)

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar()

        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(AssignmentRule.created_at.desc())

        result = await self.db.execute(query)
        rules = list(result.scalars().all())
        return rules, total

    async def create_rule(self, data: AssignmentRuleCreate, user_id: int) -> AssignmentRule:
        """Create a new assignment rule."""
        rule = AssignmentRule(**data.model_dump(), created_by_id=user_id)
        self.db.add(rule)
        await self.db.flush()
        await self.db.refresh(rule)
        return rule

    async def update_rule(self, rule: AssignmentRule, data: AssignmentRuleUpdate) -> AssignmentRule:
        """Update an assignment rule."""
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(rule, field, value)
        await self.db.flush()
        await self.db.refresh(rule)
        return rule

    async def delete_rule(self, rule: AssignmentRule) -> None:
        """Delete an assignment rule."""
        await self.db.delete(rule)
        await self.db.flush()

    def _matches_filters(self, lead_data: Dict[str, Any], filters: Dict[str, Any]) -> bool:
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

    async def _get_round_robin_user(self, rule: AssignmentRule) -> Optional[int]:
        """Get next user in round-robin rotation."""
        if not rule.user_ids:
            return None
        next_index = (rule.last_assigned_index + 1) % len(rule.user_ids)
        user_id = rule.user_ids[next_index]
        rule.last_assigned_index = next_index
        await self.db.flush()
        return user_id

    async def _get_load_balance_user(self, rule: AssignmentRule) -> Optional[int]:
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
        return min(user_lead_counts, key=user_lead_counts.get)

    async def assign_lead(self, lead_data: Dict[str, Any]) -> Optional[int]:
        """Find matching active assignment rule and return the assigned user_id.

        Returns None if no matching rule is found.
        """
        result = await self.db.execute(
            select(AssignmentRule).where(AssignmentRule.is_active == True)
            .order_by(AssignmentRule.created_at.asc())
        )
        rules = list(result.scalars().all())

        for rule in rules:
            if not self._matches_filters(lead_data, rule.filters):
                continue

            if rule.assignment_type == "round_robin":
                user_id = await self._get_round_robin_user(rule)
            elif rule.assignment_type == "load_balance":
                user_id = await self._get_load_balance_user(rule)
            else:
                continue

            if user_id is not None:
                return user_id

        return None

    async def get_assignment_stats(self, user_ids: List[int]) -> List[Dict[str, Any]]:
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
