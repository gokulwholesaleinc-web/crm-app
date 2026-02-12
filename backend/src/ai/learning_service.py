"""AI Learning Service for building user-specific context over time."""

from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional
from sqlalchemy import select, func, and_, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from src.ai.models import AILearning, AIInteractionLog
from src.contacts.models import Contact
from src.leads.models import Lead
from src.opportunities.models import Opportunity, PipelineStage
from src.activities.models import Activity
from src.companies.models import Company


class AILearningService:
    """Manages AI learnings, interaction tracking, and smart suggestions."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # =========================================================================
    # Learning CRUD
    # =========================================================================

    async def learn_preference(
        self,
        user_id: int,
        category: str,
        key: str,
        value: str,
    ) -> AILearning:
        """Store or reinforce a learning for a user."""
        result = await self.db.execute(
            select(AILearning).where(
                AILearning.user_id == user_id,
                AILearning.category == category,
                AILearning.key == key,
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.value = value
            existing.times_reinforced += 1
            existing.confidence = min(1.0, existing.confidence + 0.1)
            existing.last_used_at = datetime.now(timezone.utc)
            await self.db.flush()
            await self.db.refresh(existing)
            return existing

        learning = AILearning(
            user_id=user_id,
            category=category,
            key=key,
            value=value,
            confidence=1.0,
            times_reinforced=1,
            last_used_at=datetime.now(timezone.utc),
        )
        self.db.add(learning)
        await self.db.flush()
        await self.db.refresh(learning)
        return learning

    async def get_learnings(
        self,
        user_id: int,
        category: Optional[str] = None,
        min_confidence: float = 0.3,
    ) -> List[AILearning]:
        """Get all learnings for a user, optionally filtered by category."""
        query = (
            select(AILearning)
            .where(
                AILearning.user_id == user_id,
                AILearning.confidence >= min_confidence,
            )
            .order_by(AILearning.confidence.desc(), AILearning.times_reinforced.desc())
        )

        if category:
            query = query.where(AILearning.category == category)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def delete_learning(self, learning_id: int, user_id: int) -> bool:
        """Delete a specific learning. Returns True if deleted."""
        result = await self.db.execute(
            select(AILearning).where(
                AILearning.id == learning_id,
                AILearning.user_id == user_id,
            )
        )
        learning = result.scalar_one_or_none()
        if not learning:
            return False
        await self.db.delete(learning)
        await self.db.flush()
        return True

    async def reinforce_learning(self, learning_id: int) -> Optional[AILearning]:
        """Increase confidence when a learning is confirmed again."""
        result = await self.db.execute(
            select(AILearning).where(AILearning.id == learning_id)
        )
        learning = result.scalar_one_or_none()
        if not learning:
            return None

        learning.times_reinforced += 1
        learning.confidence = min(1.0, learning.confidence + 0.1)
        learning.last_used_at = datetime.now(timezone.utc)
        await self.db.flush()
        await self.db.refresh(learning)
        return learning

    # =========================================================================
    # Context generation for system prompt
    # =========================================================================

    async def get_user_context(self, user_id: int) -> str:
        """Build a context string from all learnings for injection into system prompt."""
        learnings = await self.get_learnings(user_id, min_confidence=0.3)

        if not learnings:
            return ""

        parts = []

        # Group by category
        preferences = [l for l in learnings if l.category == "preference"]
        patterns = [l for l in learnings if l.category == "pattern"]
        corrections = [l for l in learnings if l.category == "correction"]
        entity_context = [l for l in learnings if l.category == "entity_context"]

        if preferences:
            pref_lines = [f"- {l.key}: {l.value}" for l in preferences[:10]]
            parts.append("User preferences:\n" + "\n".join(pref_lines))

        if corrections:
            corr_lines = [f"- {l.key}: {l.value}" for l in corrections[:5]]
            parts.append("Previous corrections (important):\n" + "\n".join(corr_lines))

        if entity_context:
            ctx_lines = [f"- {l.key}: {l.value}" for l in entity_context[:5]]
            parts.append("Entity context:\n" + "\n".join(ctx_lines))

        if patterns:
            pat_lines = [f"- {l.key}: {l.value}" for l in patterns[:5]]
            parts.append("Usage patterns:\n" + "\n".join(pat_lines))

        # Get frequently accessed entities
        freq_entities = await self.get_frequently_accessed_entities(user_id)
        if freq_entities:
            freq_parts = []
            for entity_type, entities in freq_entities.items():
                names = ", ".join(entities[:3])
                freq_parts.append(f"- Frequently accessed {entity_type}: {names}")
            if freq_parts:
                parts.append("Frequently accessed:\n" + "\n".join(freq_parts))

        return "\n\n".join(parts)

    # =========================================================================
    # Interaction tracking
    # =========================================================================

    async def log_interaction(
        self,
        user_id: int,
        query: str,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
    ) -> AIInteractionLog:
        """Log an interaction for pattern analysis."""
        log = AIInteractionLog(
            user_id=user_id,
            query=query,
            tool_calls=tool_calls,
        )
        self.db.add(log)
        await self.db.flush()
        await self.db.refresh(log)
        return log

    async def learn_from_feedback(
        self,
        user_id: int,
        query: str,
        response: str,
        feedback_type: str,
        correction: Optional[str] = None,
    ) -> Optional[AILearning]:
        """Extract and store learnings from user feedback."""
        if feedback_type == "correction" and correction:
            return await self.learn_preference(
                user_id=user_id,
                category="correction",
                key=query[:200],
                value=correction[:500],
            )
        return None

    async def get_frequently_accessed_entities(self, user_id: int) -> Dict[str, List[str]]:
        """Return user's most accessed entities from interaction logs."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)

        result = await self.db.execute(
            select(AIInteractionLog)
            .where(
                AIInteractionLog.user_id == user_id,
                AIInteractionLog.created_at > cutoff,
                AIInteractionLog.tool_calls.isnot(None),
            )
            .order_by(AIInteractionLog.created_at.desc())
            .limit(50)
        )
        logs = result.scalars().all()

        # Count entity mentions from tool calls
        entity_counts: Dict[str, Dict[str, int]] = {}
        for log in logs:
            if not log.tool_calls:
                continue
            calls = log.tool_calls if isinstance(log.tool_calls, list) else [log.tool_calls]
            for call in calls:
                func_name = call.get("function", "")
                if "contact" in func_name:
                    entity_counts.setdefault("contacts", {})
                elif "lead" in func_name:
                    entity_counts.setdefault("leads", {})
                elif "opportunity" in func_name or "pipeline" in func_name:
                    entity_counts.setdefault("opportunities", {})

        return {k: list(v.keys())[:3] for k, v in entity_counts.items() if v}

    # =========================================================================
    # Confidence decay
    # =========================================================================

    async def decay_old_learnings(self, days_threshold: int = 60) -> int:
        """Reduce confidence of old, unused learnings. Returns count of decayed items."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_threshold)

        result = await self.db.execute(
            select(AILearning).where(
                AILearning.last_used_at < cutoff,
                AILearning.confidence > 0.1,
            )
        )
        old_learnings = result.scalars().all()

        count = 0
        for learning in old_learnings:
            learning.confidence = max(0.1, learning.confidence - 0.2)
            count += 1

        if count > 0:
            await self.db.flush()

        return count

    # =========================================================================
    # Smart suggestions
    # =========================================================================

    async def generate_smart_suggestions(self, user_id: int) -> List[Dict[str, Any]]:
        """Generate personalized suggestions based on user data and patterns."""
        suggestions = []

        # Check for contacts/leads without recent follow-up
        await self._suggest_stale_followups(user_id, suggestions)

        # Check for expiring quotes
        await self._suggest_expiring_quotes(user_id, suggestions)

        # Check pipeline health
        await self._suggest_pipeline_actions(user_id, suggestions)

        # Check overdue activities
        await self._suggest_overdue_activities(user_id, suggestions)

        return suggestions[:10]

    async def _suggest_stale_followups(
        self, user_id: int, suggestions: List[Dict[str, Any]]
    ) -> None:
        """Suggest follow-ups for stale contacts."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=5)

        # Find contacts with opportunities but no recent activity
        result = await self.db.execute(
            select(Contact)
            .join(Opportunity, Opportunity.contact_id == Contact.id)
            .join(PipelineStage, Opportunity.pipeline_stage_id == PipelineStage.id)
            .where(
                Opportunity.owner_id == user_id,
                PipelineStage.is_won == False,
                PipelineStage.is_lost == False,
            )
            .limit(5)
        )
        contacts = result.scalars().all()

        for contact in contacts:
            activity_result = await self.db.execute(
                select(func.count(Activity.id))
                .where(
                    Activity.entity_type == "contacts",
                    Activity.entity_id == contact.id,
                    Activity.created_at > cutoff,
                )
            )
            recent_count = activity_result.scalar() or 0

            if recent_count == 0:
                suggestions.append({
                    "type": "follow_up",
                    "priority": "medium",
                    "title": f"Follow up with {contact.full_name}",
                    "description": f"No recent activity with {contact.full_name} who has open deals.",
                    "action": "schedule_call",
                    "entity_type": "contacts",
                    "entity_id": contact.id,
                })

    async def _suggest_expiring_quotes(
        self, user_id: int, suggestions: List[Dict[str, Any]]
    ) -> None:
        """Suggest action on quotes expiring soon."""
        from src.quotes.models import Quote

        today = datetime.now(timezone.utc).date()
        week_out = today + timedelta(days=7)

        result = await self.db.execute(
            select(Quote)
            .where(
                Quote.owner_id == user_id,
                Quote.status == "sent",
                Quote.valid_until <= week_out,
                Quote.valid_until >= today,
            )
            .limit(5)
        )
        quotes = result.scalars().all()

        for quote in quotes:
            days_left = (quote.valid_until - today).days if quote.valid_until else 0
            suggestions.append({
                "type": "expiring_quote",
                "priority": "high",
                "title": f"Quote '{quote.title}' expires in {days_left} days",
                "description": f"Send a reminder or follow up before it expires.",
                "action": "send_reminder",
                "entity_type": "quotes",
                "entity_id": quote.id,
            })

    async def _suggest_pipeline_actions(
        self, user_id: int, suggestions: List[Dict[str, Any]]
    ) -> None:
        """Suggest actions based on pipeline health."""
        result = await self.db.execute(
            select(
                func.sum(Opportunity.amount),
                func.count(Opportunity.id),
            )
            .join(PipelineStage)
            .where(
                Opportunity.owner_id == user_id,
                PipelineStage.is_won == False,
                PipelineStage.is_lost == False,
            )
        )
        row = result.one_or_none()
        if row and row[1] and row[1] > 0:
            total_value = float(row[0] or 0)
            deal_count = row[1]
            avg_deal = total_value / deal_count if deal_count else 0

            if deal_count > 0 and total_value > 0:
                suggestions.append({
                    "type": "pipeline_insight",
                    "priority": "low",
                    "title": f"Pipeline: {deal_count} open deals worth ${total_value:,.0f}",
                    "description": f"Average deal size: ${avg_deal:,.0f}. Review your pipeline for next steps.",
                    "action": "review_pipeline",
                    "entity_type": "opportunities",
                    "entity_id": None,
                })

    async def _suggest_overdue_activities(
        self, user_id: int, suggestions: List[Dict[str, Any]]
    ) -> None:
        """Suggest completing overdue activities."""
        today = datetime.now(timezone.utc).date()

        result = await self.db.execute(
            select(func.count(Activity.id))
            .where(
                Activity.owner_id == user_id,
                Activity.is_completed == False,
                Activity.due_date < today,
            )
        )
        overdue_count = result.scalar() or 0

        if overdue_count > 0:
            suggestions.append({
                "type": "overdue_tasks",
                "priority": "high",
                "title": f"You have {overdue_count} overdue task(s)",
                "description": "Review and complete or reschedule your overdue tasks.",
                "action": "view_tasks",
                "entity_type": "activities",
                "entity_id": None,
            })

    # =========================================================================
    # Entity insights
    # =========================================================================

    async def get_entity_insights(
        self, entity_type: str, entity_id: int, user_id: int
    ) -> Dict[str, Any]:
        """Get AI-powered insights for a specific entity."""
        insights = {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "insights": [],
            "suggestions": [],
        }

        # Activity count
        activity_result = await self.db.execute(
            select(func.count(Activity.id))
            .where(
                Activity.entity_type == entity_type,
                Activity.entity_id == entity_id,
            )
        )
        activity_count = activity_result.scalar() or 0

        # Recent activity
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        recent_result = await self.db.execute(
            select(func.count(Activity.id))
            .where(
                Activity.entity_type == entity_type,
                Activity.entity_id == entity_id,
                Activity.created_at > cutoff,
            )
        )
        recent_count = recent_result.scalar() or 0

        insights["insights"].append({
            "label": "Total activities",
            "value": activity_count,
        })
        insights["insights"].append({
            "label": "Activities this week",
            "value": recent_count,
        })

        if recent_count == 0 and activity_count > 0:
            insights["suggestions"].append(
                "No recent activity - consider scheduling a follow-up."
            )
        elif activity_count == 0:
            insights["suggestions"].append(
                "No activities recorded yet - make initial contact."
            )

        # Entity-specific insights
        if entity_type == "opportunities":
            opp_result = await self.db.execute(
                select(Opportunity).where(Opportunity.id == entity_id)
            )
            opp = opp_result.scalar_one_or_none()
            if opp:
                if opp.expected_close_date:
                    from datetime import date as date_type
                    days_to_close = (opp.expected_close_date - date_type.today()).days
                    if days_to_close < 0:
                        insights["suggestions"].append(
                            f"Deal is {abs(days_to_close)} days past expected close date."
                        )
                    elif days_to_close <= 7:
                        insights["suggestions"].append(
                            f"Deal closes in {days_to_close} days - push for commitment."
                        )

        return insights
