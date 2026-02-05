"""AI-powered recommendations for CRM actions."""

from typing import Dict, Any, List
from datetime import datetime, timedelta
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.constants import ErrorMessages, EntityNames
from src.leads.models import Lead
from src.opportunities.models import Opportunity, PipelineStage
from src.activities.models import Activity
from src.contacts.models import Contact


class RecommendationEngine:
    """Generates recommendations for CRM users."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_recommendations(self, user_id: int) -> List[Dict[str, Any]]:
        """Get prioritized recommendations for the user."""
        recommendations = []

        # Check for overdue tasks
        overdue_recs = await self._check_overdue_tasks(user_id)
        recommendations.extend(overdue_recs)

        # Check for stale leads
        stale_lead_recs = await self._check_stale_leads(user_id)
        recommendations.extend(stale_lead_recs)

        # Check for deals at risk
        at_risk_recs = await self._check_at_risk_deals(user_id)
        recommendations.extend(at_risk_recs)

        # Check for hot leads without follow-up
        hot_lead_recs = await self._check_hot_leads_no_activity(user_id)
        recommendations.extend(hot_lead_recs)

        # Sort by priority
        priority_order = {"high": 0, "medium": 1, "low": 2}
        recommendations.sort(key=lambda x: priority_order.get(x.get("priority", "low"), 2))

        return recommendations[:10]  # Return top 10

    async def _check_overdue_tasks(self, user_id: int) -> List[Dict[str, Any]]:
        """Check for overdue tasks."""
        today = datetime.now().date()

        result = await self.db.execute(
            select(Activity)
            .where(
                or_(
                    Activity.owner_id == user_id,
                    Activity.assigned_to_id == user_id,
                )
            )
            .where(Activity.is_completed == False)
            .where(Activity.due_date < today)
            .order_by(Activity.due_date.asc())
            .limit(5)
        )

        overdue_tasks = result.scalars().all()
        recommendations = []

        for task in overdue_tasks:
            days_overdue = (today - task.due_date).days
            recommendations.append({
                "type": "overdue_task",
                "priority": "high",
                "title": f"Overdue: {task.subject}",
                "description": f"This task is {days_overdue} days overdue",
                "action": "Complete or reschedule",
                "entity_type": task.entity_type,
                "entity_id": task.entity_id,
                "activity_id": task.id,
            })

        return recommendations

    async def _check_stale_leads(self, user_id: int) -> List[Dict[str, Any]]:
        """Check for leads with no recent activity."""
        cutoff = datetime.now() - timedelta(days=14)

        # Get leads owned by user with no recent activity
        result = await self.db.execute(
            select(Lead)
            .where(Lead.owner_id == user_id)
            .where(Lead.status.in_(["new", "contacted"]))
            .where(Lead.updated_at < cutoff)
            .limit(5)
        )

        stale_leads = result.scalars().all()
        recommendations = []

        for lead in stale_leads:
            days_stale = (datetime.now() - lead.updated_at.replace(tzinfo=None)).days
            recommendations.append({
                "type": "stale_lead",
                "priority": "medium",
                "title": f"Follow up with {lead.full_name}",
                "description": f"No activity in {days_stale} days. Consider reaching out.",
                "action": "Schedule a follow-up call or email",
                "entity_type": "leads",
                "entity_id": lead.id,
            })

        return recommendations

    async def _check_at_risk_deals(self, user_id: int) -> List[Dict[str, Any]]:
        """Check for deals that might be at risk."""
        today = datetime.now().date()

        # Deals past expected close date
        result = await self.db.execute(
            select(Opportunity)
            .join(PipelineStage)
            .where(Opportunity.owner_id == user_id)
            .where(PipelineStage.is_won == False)
            .where(PipelineStage.is_lost == False)
            .where(Opportunity.expected_close_date < today)
            .limit(5)
        )

        at_risk = result.scalars().all()
        recommendations = []

        for opp in at_risk:
            days_past = (today - opp.expected_close_date).days
            recommendations.append({
                "type": "at_risk_deal",
                "priority": "high",
                "title": f"Deal at risk: {opp.name}",
                "description": f"Expected close date was {days_past} days ago",
                "action": "Update timeline or take action to close",
                "entity_type": "opportunities",
                "entity_id": opp.id,
                "amount": opp.amount,
            })

        return recommendations

    async def _check_hot_leads_no_activity(self, user_id: int) -> List[Dict[str, Any]]:
        """Check for high-scoring leads without recent follow-up."""
        cutoff = datetime.now() - timedelta(days=7)

        # Get high-score leads
        result = await self.db.execute(
            select(Lead)
            .where(Lead.owner_id == user_id)
            .where(Lead.score >= 50)
            .where(Lead.status.in_(["new", "contacted", "qualified"]))
            .limit(10)
        )

        hot_leads = result.scalars().all()
        recommendations = []

        for lead in hot_leads:
            # Check for recent activity
            activity_result = await self.db.execute(
                select(func.count(Activity.id))
                .where(Activity.entity_type == "leads")
                .where(Activity.entity_id == lead.id)
                .where(Activity.created_at > cutoff)
            )
            recent_count = activity_result.scalar() or 0

            if recent_count == 0:
                recommendations.append({
                    "type": "hot_lead_no_activity",
                    "priority": "medium",
                    "title": f"Hot lead needs attention: {lead.full_name}",
                    "description": f"Score: {lead.score}. No activity in the last week.",
                    "action": "Reach out to maintain momentum",
                    "entity_type": "leads",
                    "entity_id": lead.id,
                    "score": lead.score,
                })

        return recommendations

    async def get_next_best_action(
        self,
        entity_type: str,
        entity_id: int,
    ) -> Dict[str, Any]:
        """Get the recommended next action for an entity."""
        if entity_type == "leads":
            return await self._get_lead_next_action(entity_id)
        elif entity_type == "opportunities":
            return await self._get_opportunity_next_action(entity_id)
        elif entity_type == "contacts":
            return await self._get_contact_next_action(entity_id)
        else:
            return {"action": "Review and update", "reason": "Keep records current"}

    async def _get_lead_next_action(self, lead_id: int) -> Dict[str, Any]:
        """Get next best action for a lead."""
        result = await self.db.execute(
            select(Lead).where(Lead.id == lead_id)
        )
        lead = result.scalar_one_or_none()

        if not lead:
            return {"error": ErrorMessages.not_found(EntityNames.LEAD)}

        # Check last activity
        last_activity = await self.db.execute(
            select(Activity)
            .where(Activity.entity_type == "leads", Activity.entity_id == lead_id)
            .order_by(Activity.created_at.desc())
            .limit(1)
        )
        last = last_activity.scalar_one_or_none()

        if lead.status == "new":
            return {
                "action": "Make initial contact",
                "activity_type": "call",
                "reason": "New lead needs first touchpoint",
            }
        elif lead.status == "contacted":
            if last and last.activity_type == "call":
                return {
                    "action": "Send follow-up email",
                    "activity_type": "email",
                    "reason": "Follow up on initial call",
                }
            else:
                return {
                    "action": "Schedule qualification call",
                    "activity_type": "call",
                    "reason": "Determine if lead is qualified",
                }
        elif lead.status == "qualified":
            return {
                "action": "Convert to opportunity",
                "activity_type": "task",
                "reason": "Lead is qualified and ready for pipeline",
            }
        else:
            return {
                "action": "Review lead status",
                "activity_type": "task",
                "reason": "Determine appropriate next steps",
            }

    async def _get_opportunity_next_action(self, opp_id: int) -> Dict[str, Any]:
        """Get next best action for an opportunity."""
        result = await self.db.execute(
            select(Opportunity).where(Opportunity.id == opp_id)
        )
        opp = result.scalar_one_or_none()

        if not opp:
            return {"error": ErrorMessages.not_found(EntityNames.OPPORTUNITY)}

        stage = opp.pipeline_stage

        if stage.probability < 25:
            return {
                "action": "Schedule discovery meeting",
                "activity_type": "meeting",
                "reason": "Understand requirements better",
            }
        elif stage.probability < 50:
            return {
                "action": "Send proposal",
                "activity_type": "email",
                "reason": "Move deal forward with concrete offer",
            }
        elif stage.probability < 75:
            return {
                "action": "Handle objections call",
                "activity_type": "call",
                "reason": "Address any concerns before closing",
            }
        else:
            return {
                "action": "Close the deal",
                "activity_type": "task",
                "reason": "High probability - push for signature",
            }

    async def _get_contact_next_action(self, contact_id: int) -> Dict[str, Any]:
        """Get next best action for a contact."""
        # Check for recent activity
        cutoff = datetime.now() - timedelta(days=30)

        activity_result = await self.db.execute(
            select(func.count(Activity.id))
            .where(Activity.entity_type == "contacts")
            .where(Activity.entity_id == contact_id)
            .where(Activity.created_at > cutoff)
        )
        recent_count = activity_result.scalar() or 0

        if recent_count == 0:
            return {
                "action": "Check in with contact",
                "activity_type": "email",
                "reason": "Maintain relationship with periodic touchpoint",
            }
        else:
            return {
                "action": "Review notes and plan next touchpoint",
                "activity_type": "note",
                "reason": "Keep relationship active",
            }
