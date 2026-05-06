"""Activity timeline utilities."""

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.activities.models import Activity


class ActivityTimeline:
    """Generates unified activity timeline for entities."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_entity_timeline(
        self,
        entity_type: str,
        entity_id: int,
        limit: int = 50,
        activity_types: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get activity timeline for a specific entity.

        Returns activities sorted by date (most recent first).
        """
        query = (
            select(Activity)
            .where(Activity.entity_type == entity_type)
            .where(Activity.entity_id == entity_id)
        )

        if activity_types:
            query = query.where(Activity.activity_type.in_(activity_types))

        query = query.order_by(Activity.created_at.desc()).limit(limit)

        result = await self.db.execute(query)
        activities = result.scalars().all()

        return [self._format_activity(a) for a in activities]

    async def get_user_timeline(
        self,
        user_id: int,
        limit: int = 50,
        include_assigned: bool = True,
        activity_types: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get activity timeline for a user (owned or assigned activities).
        """
        conditions = [Activity.owner_id == user_id]
        if include_assigned:
            conditions.append(Activity.assigned_to_id == user_id)

        query = select(Activity).where(or_(*conditions))

        if activity_types:
            query = query.where(Activity.activity_type.in_(activity_types))

        query = query.order_by(Activity.created_at.desc()).limit(limit)

        result = await self.db.execute(query)
        activities = result.scalars().all()

        return [self._format_activity(a) for a in activities]

    async def get_upcoming_activities(
        self,
        user_id: int,
        days_ahead: int = 7,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """
        Get upcoming scheduled activities for a user.
        """
        now = datetime.now()
        future = now + timedelta(days=days_ahead)

        query = (
            select(Activity)
            .where(
                or_(
                    Activity.owner_id == user_id,
                    Activity.assigned_to_id == user_id,
                )
            )
            .where(Activity.is_completed == False)
            .where(
                or_(
                    and_(
                        Activity.scheduled_at.is_not(None),
                        Activity.scheduled_at >= now,
                        Activity.scheduled_at <= future,
                    ),
                    and_(
                        Activity.due_date.is_not(None),
                        Activity.due_date >= now.date(),
                        Activity.due_date <= future.date(),
                    ),
                )
            )
            .order_by(Activity.scheduled_at.asc().nullslast(), Activity.due_date.asc().nullslast())
            .limit(limit)
        )

        result = await self.db.execute(query)
        activities = result.scalars().all()

        return [self._format_activity(a) for a in activities]

    async def get_overdue_tasks(
        self,
        user_id: int,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """
        Get overdue tasks for a user.
        """
        today = datetime.now().date()

        query = (
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
            .limit(limit)
        )

        result = await self.db.execute(query)
        activities = result.scalars().all()

        return [self._format_activity(a) for a in activities]

    async def get_unified_timeline(
        self,
        entity_type: str,
        entity_id: int,
        limit: int = 50,
        viewer_user_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """Get a unified timeline combining activities, emails, and sequence events for an entity.

        Returns all event types sorted by timestamp (most recent first).

        ``viewer_user_id`` enables the same participant-based scoping the
        ``/api/email/thread`` endpoint uses: emails are only included if
        the viewer composed them or is on the participant set. Pass
        ``None`` for admin / unscoped reads.
        """
        events: list[dict[str, Any]] = []

        # 1. Activities
        activity_result = await self.db.execute(
            select(Activity)
            .where(Activity.entity_type == entity_type, Activity.entity_id == entity_id)
            .order_by(Activity.created_at.desc())
            .limit(limit)
        )
        for a in activity_result.scalars().all():
            events.append({
                "id": a.id,
                "event_type": "activity",
                "subject": a.subject or a.activity_type,
                "description": a.description,
                "entity_type": a.entity_type,
                "entity_id": a.entity_id,
                "timestamp": a.created_at.isoformat(),
                "metadata": {"activity_type": a.activity_type, "is_completed": a.is_completed, "priority": a.priority},
            })

        # 2. Emails sent to this entity (scoped by participant overlap so
        # non-admin viewers don't see threads ingested via teammates'
        # Gmail connections — same invariant as /api/email/thread).
        from src.email.models import EmailQueue
        email_filters = [
            EmailQueue.entity_type == entity_type,
            EmailQueue.entity_id == entity_id,
        ]
        if viewer_user_id is not None:
            from src.email.participants import get_user_connection_emails
            from src.email.service import _outbound_visibility_clause
            viewer_emails = await get_user_connection_emails(self.db, viewer_user_id)
            email_filters.append(
                _outbound_visibility_clause(viewer_user_id, viewer_emails)
            )
        email_result = await self.db.execute(
            select(EmailQueue)
            .where(*email_filters)
            .order_by(EmailQueue.created_at.desc())
            .limit(limit)
        )
        for e in email_result.scalars().all():
            event_type = "email_sent"
            if e.opened_at:
                event_type = "email_opened"
            if e.clicked_at:
                event_type = "email_clicked"

            events.append({
                "id": e.id,
                "event_type": event_type,
                "subject": f"Email: {e.subject}",
                "description": f"To: {e.to_email} — Status: {e.status}",
                "entity_type": e.entity_type,
                "entity_id": e.entity_id,
                "timestamp": (e.sent_at or e.created_at).isoformat(),
                "metadata": {
                    "status": e.status,
                    "open_count": e.open_count,
                    "click_count": e.click_count,
                    "campaign_id": e.campaign_id,
                },
            })

        # 3. Sequence enrollments for contacts
        if entity_type in ("contacts", "contact"):
            from src.sequences.models import Sequence, SequenceEnrollment
            enrollment_result = await self.db.execute(
                select(SequenceEnrollment, Sequence.name)
                .join(Sequence, SequenceEnrollment.sequence_id == Sequence.id)
                .where(SequenceEnrollment.contact_id == entity_id)
                .order_by(SequenceEnrollment.started_at.desc())
                .limit(limit)
            )
            for enrollment, seq_name in enrollment_result.all():
                events.append({
                    "id": enrollment.id,
                    "event_type": "sequence_step",
                    "subject": f"Sequence: {seq_name}",
                    "description": f"Step {enrollment.current_step} — Status: {enrollment.status}",
                    "entity_type": "contacts",
                    "entity_id": entity_id,
                    "timestamp": enrollment.started_at.isoformat(),
                    "metadata": {
                        "sequence_id": enrollment.sequence_id,
                        "current_step": enrollment.current_step,
                        "status": enrollment.status,
                    },
                })

        # Sort all events by timestamp descending
        events.sort(key=lambda x: x["timestamp"], reverse=True)
        return events[:limit]

    def _format_activity(self, activity: Activity) -> dict[str, Any]:
        """Format activity for timeline display."""
        return {
            "id": activity.id,
            "activity_type": activity.activity_type,
            "subject": activity.subject,
            "description": activity.description,
            "entity_type": activity.entity_type,
            "entity_id": activity.entity_id,
            "scheduled_at": activity.scheduled_at.isoformat() if activity.scheduled_at else None,
            "due_date": activity.due_date.isoformat() if activity.due_date else None,
            "completed_at": activity.completed_at.isoformat() if activity.completed_at else None,
            "is_completed": activity.is_completed,
            "priority": activity.priority,
            "created_at": activity.created_at.isoformat(),
            "owner_id": activity.owner_id,
            "assigned_to_id": activity.assigned_to_id,
            # Type-specific fields
            "call_duration_minutes": activity.call_duration_minutes,
            "call_outcome": activity.call_outcome,
            "meeting_location": activity.meeting_location,
        }
