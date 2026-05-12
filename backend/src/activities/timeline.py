"""Activity timeline utilities."""

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.activities.models import Activity

# Entity types the frontend has a detail-page route for. Used to decide
# whether the dashboard "Recent Activities" row should render a link;
# unrouteable types still get an entity_label but no entity_link.
# Keep in sync with frontend/src/routes/index.tsx.
_ROUTABLE_ENTITY_PLURALS: dict[str, str] = {
    "contacts": "/contacts",
    "companies": "/companies",
    "leads": "/leads",
    "opportunities": "/opportunities",
    "quotes": "/quotes",
    "proposals": "/proposals",
    "contracts": "/contracts",
    "payments": "/payments",
}

# Tolerant alias map covering historical singular spellings the activity
# table may have stored. Resolves to the canonical plural used above.
_ENTITY_ALIASES: dict[str, str] = {
    "contact": "contacts",
    "company": "companies",
    "lead": "leads",
    "opportunity": "opportunities",
    "quote": "quotes",
    "proposal": "proposals",
    "contract": "contracts",
    "payment": "payments",
}


def _canonical_plural(entity_type: str | None) -> str | None:
    if not entity_type:
        return None
    if entity_type in _ROUTABLE_ENTITY_PLURALS:
        return entity_type
    return _ENTITY_ALIASES.get(entity_type)


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

        formatted = [self._format_activity(a) for a in activities]
        await self._enrich_with_owner_and_entity(formatted)
        return formatted

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

        formatted = [self._format_activity(a) for a in activities]
        await self._enrich_with_owner_and_entity(formatted)
        return formatted

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

        formatted = [self._format_activity(a) for a in activities]
        await self._enrich_with_owner_and_entity(formatted)
        return formatted

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

        formatted = [self._format_activity(a) for a in activities]
        await self._enrich_with_owner_and_entity(formatted)
        return formatted

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
            from src.email.service import _dialect_name, _outbound_visibility_clause
            viewer_emails = await get_user_connection_emails(self.db, viewer_user_id)
            email_filters.append(
                _outbound_visibility_clause(
                    viewer_user_id, viewer_emails, _dialect_name(self.db)
                )
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
            "owner_name": None,
            "entity_label": None,
            "entity_link": None,
            # Type-specific fields
            "call_duration_minutes": activity.call_duration_minutes,
            "call_outcome": activity.call_outcome,
            "meeting_location": activity.meeting_location,
        }

    async def _enrich_with_owner_and_entity(self, items: list[dict[str, Any]]) -> None:
        """Populate ``owner_name`` and ``entity_label`` on already-formatted items.

        Batches lookups by entity_type so a 50-item timeline costs ~5 SELECTs
        regardless of mix. Unknown entity_type rows get a "{Type} #{id}"
        fallback so the UI can still render a link.
        """
        if not items:
            return

        await self._fill_owner_names(items)
        await self._fill_entity_labels(items)

    async def _fill_owner_names(self, items: list[dict[str, Any]]) -> None:
        from src.auth.models import User

        owner_ids = {i["owner_id"] for i in items if i.get("owner_id")}
        if not owner_ids:
            return
        result = await self.db.execute(
            select(User.id, User.full_name).where(User.id.in_(owner_ids))
        )
        name_by_id = {row[0]: row[1] for row in result.all()}
        for item in items:
            owner_id = item.get("owner_id")
            if owner_id is not None:
                item["owner_name"] = name_by_id.get(owner_id)

    async def _fill_entity_labels(self, items: list[dict[str, Any]]) -> None:
        """Resolve display label + URL path for each row's polymorphic entity.

        Only entity types the frontend has a detail route for get a label
        and link. Unrouteable types are left as None so the UI shows the
        activity subject without a broken-link "→ Foo #42" affordance.
        """
        ids_by_type: dict[str, set[int]] = defaultdict(set)
        for item in items:
            plural = _canonical_plural(item.get("entity_type"))
            eid = item.get("entity_id")
            if plural and eid:
                ids_by_type[plural].add(eid)

        label_lookup: dict[tuple[str, int], str] = {}
        for plural, ids in ids_by_type.items():
            label_lookup.update(await self._labels_for(plural, ids))

        for item in items:
            plural = _canonical_plural(item.get("entity_type"))
            eid = item.get("entity_id")
            if not (plural and eid):
                continue
            url_prefix = _ROUTABLE_ENTITY_PLURALS[plural]
            item["entity_label"] = label_lookup.get((plural, eid)) or self._fallback_label(plural, eid)
            item["entity_link"] = f"{url_prefix}/{eid}"

    async def _labels_for(
        self, entity_type: str, ids: set[int]
    ) -> dict[tuple[str, int], str]:
        """Return {(entity_type, id): label} for one entity_type in one query.

        ``entity_type`` is the canonical plural (e.g. "contacts"). Each
        branch is a single batched SELECT; types without a branch fall
        through to :meth:`_fallback_label` via the caller.
        """
        if not ids:
            return {}

        if entity_type == "contacts":
            from src.contacts.models import Contact
            rows = await self.db.execute(
                select(Contact.id, Contact.first_name, Contact.last_name).where(
                    Contact.id.in_(ids)
                )
            )
            return {
                (entity_type, row[0]): f"{row[1] or ''} {row[2] or ''}".strip() or f"Contact #{row[0]}"
                for row in rows.all()
            }
        if entity_type == "leads":
            from src.leads.models import Lead
            rows = await self.db.execute(
                select(Lead.id, Lead.first_name, Lead.last_name).where(Lead.id.in_(ids))
            )
            return {
                (entity_type, row[0]): f"{row[1] or ''} {row[2] or ''}".strip() or f"Lead #{row[0]}"
                for row in rows.all()
            }
        if entity_type == "opportunities":
            from src.opportunities.models import Opportunity
            rows = await self.db.execute(
                select(Opportunity.id, Opportunity.name).where(Opportunity.id.in_(ids))
            )
            return {(entity_type, row[0]): row[1] for row in rows.all()}
        if entity_type == "companies":
            from src.companies.models import Company
            rows = await self.db.execute(
                select(Company.id, Company.name).where(Company.id.in_(ids))
            )
            return {(entity_type, row[0]): row[1] for row in rows.all()}
        if entity_type == "quotes":
            from src.quotes.models import Quote
            rows = await self.db.execute(
                select(Quote.id, Quote.quote_number).where(Quote.id.in_(ids))
            )
            return {(entity_type, row[0]): row[1] for row in rows.all()}
        if entity_type == "proposals":
            from src.proposals.models import Proposal
            rows = await self.db.execute(
                select(Proposal.id, Proposal.title).where(Proposal.id.in_(ids))
            )
            return {(entity_type, row[0]): row[1] for row in rows.all()}
        if entity_type == "contracts":
            from src.contracts.models import Contract
            rows = await self.db.execute(
                select(Contract.id, Contract.title).where(Contract.id.in_(ids))
            )
            return {(entity_type, row[0]): row[1] for row in rows.all()}

        return {}

    @staticmethod
    def _fallback_label(entity_type: str, entity_id: int) -> str:
        return f"{entity_type.rstrip('s').capitalize()} #{entity_id}"
