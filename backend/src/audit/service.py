"""Audit services for recording entity changes and active CRM work time."""

import logging
from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from sqlalchemy import String, cast, func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from src.activities.models import Activity
from src.audit.models import AuditLog, WorkSession
from src.auth.models import User
from src.core.constants import DEFAULT_PAGE_SIZE
from src.core.entity_types import canonical_plural, canonical_singular, entity_type_variants

WORK_SESSION_IDLE_TIMEOUT_SECONDS = 5 * 60


class AuditService:
    """Service for audit log operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def log_change(
        self,
        entity_type: str,
        entity_id: int,
        user_id: int | None,
        action: str,
        changes: list[dict] | None = None,
        ip_address: str | None = None,
    ) -> AuditLog:
        """Record an audit log entry."""
        entry = AuditLog(
            entity_type=entity_type,
            entity_id=entity_id,
            user_id=user_id,
            action=action,
            changes=changes,
            ip_address=ip_address,
        )
        self.db.add(entry)
        await self.db.flush()
        await self.db.refresh(entry)
        return entry

    async def get_entity_history(
        self,
        entity_type: str,
        entity_id: int,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> tuple[list[dict], int]:
        """Get paginated audit history for a specific entity."""
        base_filter = [
            AuditLog.entity_type == entity_type,
            AuditLog.entity_id == entity_id,
        ]

        # Count
        count_query = select(func.count()).select_from(
            select(AuditLog.id).where(*base_filter).subquery()
        )
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Fetch with user name join
        query = (
            select(AuditLog, User.full_name.label("user_name"))
            .outerjoin(User, AuditLog.user_id == User.id)
            .where(*base_filter)
            .order_by(AuditLog.timestamp.desc(), AuditLog.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self.db.execute(query)
        rows = result.all()

        items = []
        for log, user_name in rows:
            items.append({
                "id": log.id,
                "entity_type": log.entity_type,
                "entity_id": log.entity_id,
                "user_id": log.user_id,
                "user_name": user_name,
                "action": log.action,
                "changes": log.changes,
                "ip_address": log.ip_address,
                "created_at": log.timestamp,
            })

        return items, total

    async def get_admin_feed(
        self,
        *,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
        start_date: date | None = None,
        end_date: date | None = None,
        user_id: int | None = None,
        entity_type: str | None = None,
        entity_id: int | None = None,
        action: str | None = None,
        search: str | None = None,
    ) -> tuple[list[dict], int]:
        """Get a filtered, paginated audit feed for admins."""
        conditions = self._audit_filter_conditions(
            start_date=start_date,
            end_date=end_date,
            user_id=user_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            search=search,
        )

        count_query = select(func.count()).select_from(
            select(AuditLog.id)
            .outerjoin(User, AuditLog.user_id == User.id)
            .where(*conditions)
            .subquery()
        )
        total = (await self.db.execute(count_query)).scalar() or 0

        query = (
            select(
                AuditLog,
                User.full_name.label("user_name"),
                User.email.label("user_email"),
            )
            .outerjoin(User, AuditLog.user_id == User.id)
            .where(*conditions)
            .order_by(AuditLog.timestamp.desc(), AuditLog.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = (await self.db.execute(query)).all()

        items = []
        for log, user_name, user_email in rows:
            items.append({
                "id": log.id,
                "entity_type": log.entity_type,
                "entity_id": log.entity_id,
                "user_id": log.user_id,
                "user_name": user_name,
                "user_email": user_email,
                "action": log.action,
                "changes": log.changes,
                "ip_address": log.ip_address,
                "created_at": log.timestamp,
            })
        return items, total

    async def iter_admin_feed_rows(
        self,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
        user_id: int | None = None,
        entity_type: str | None = None,
        entity_id: int | None = None,
        action: str | None = None,
        search: str | None = None,
        batch_size: int = 500,
    ):
        """Yield admin-audit rows from a server-side cursor.

        Used by the streaming CSV export so compliance pulls don't have to
        materialize the full filtered set in memory at once.
        """
        conditions = self._audit_filter_conditions(
            start_date=start_date,
            end_date=end_date,
            user_id=user_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            search=search,
        )
        # Cap cursor at 5min on Postgres. Wide-date + JSON `search`
        # casts `changes` to text and forces a full scan that can pin a
        # Neon pooler slot. SET LOCAL no-ops silently outside a txn, so
        # we verify via SHOW after — the router's broad except already
        # converts a real timeout into the CSV "EXPORT TRUNCATED"
        # trailer, but we don't want a *silent* drop to look like
        # success. get_bind() in try/except keeps a detached-session
        # bug from being laundered into the same "TRUNCATED" message.
        dialect_name: str | None = None
        try:
            dialect_name = self.db.get_bind().dialect.name
        except Exception:  # noqa: BLE001 - any bind failure → skip timeout, don't crash export
            logger.warning("audit CSV: could not resolve dialect", exc_info=True)
        if dialect_name == "postgresql":
            await self.db.execute(text("SET LOCAL statement_timeout = '300s'"))
            current = (await self.db.execute(text("SHOW statement_timeout"))).scalar()
            if current == "0":
                logger.warning(
                    "audit CSV: SET LOCAL statement_timeout did not apply "
                    "(SHOW returned '0'); cursor is unbounded"
                )
        query = (
            select(
                AuditLog,
                User.full_name.label("user_name"),
                User.email.label("user_email"),
            )
            .outerjoin(User, AuditLog.user_id == User.id)
            .where(*conditions)
            .order_by(AuditLog.timestamp.desc(), AuditLog.id.desc())
            .execution_options(yield_per=batch_size)
        )
        result = await self.db.stream(query)
        async for log, user_name, user_email in result:
            yield {
                "id": log.id,
                "entity_type": log.entity_type,
                "entity_id": log.entity_id,
                "user_id": log.user_id,
                "user_name": user_name,
                "user_email": user_email,
                "action": log.action,
                "changes": log.changes,
                "ip_address": log.ip_address,
                "created_at": log.timestamp,
            }

    async def get_admin_summary(
        self,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
        user_id: int | None = None,
        entity_type: str | None = None,
        action: str | None = None,
        search: str | None = None,
        entity_limit: int = 100,
    ) -> dict:
        """Build dashboard aggregates from audit logs, activities, and sessions.

        Defaults ``start_date`` to ``today - 30d`` when omitted so an admin
        opening ``/admin/audit`` with no filter doesn't trigger a full
        audit_logs scan. The dashboard exposes a "All time" preset that
        passes an explicit very-old start_date when the user wants
        unfiltered history; the slow query is then opt-in.
        """
        if start_date is None and end_date is None:
            start_date = (datetime.now(UTC) - timedelta(days=30)).date()
        start_at, end_at = _date_range_to_datetimes(start_date, end_date)

        users = await self._load_users()
        user_stats = _new_user_stats()
        entity_stats = _new_entity_stats()

        audit_conditions = self._audit_filter_conditions(
            start_date=start_date,
            end_date=end_date,
            user_id=user_id,
            entity_type=entity_type,
            action=action,
            search=search,
        )
        audit_rows = (
            await self.db.execute(
                select(AuditLog)
                .outerjoin(User, AuditLog.user_id == User.id)
                .where(*audit_conditions)
                .order_by(AuditLog.timestamp.desc(), AuditLog.id.desc())
            )
        ).scalars().all()

        security_events = self._build_security_events(audit_rows, users)

        for log in audit_rows:
            timestamp = log.timestamp
            if log.user_id is not None:
                stats = user_stats[log.user_id]
                stats["audit_events"] += 1
                stats["last_active_at"] = _max_dt(stats["last_active_at"], timestamp)
                singular = canonical_singular(log.entity_type)
                if singular == "proposal":
                    stats["proposals_touched"].add(log.entity_id)
                elif singular == "opportunity":
                    stats["opportunities_touched"].add(log.entity_id)

            entity_key = _entity_key(log.entity_type, log.entity_id)
            estats = entity_stats[entity_key]
            estats["audit_count"] += 1
            estats["last_touched_at"] = _max_dt(estats["last_touched_at"], timestamp)
            if estats["last_touched_by_id"] is None:
                estats["last_touched_by_id"] = log.user_id

        session_conditions = self._work_session_filter_conditions(
            start_at=start_at,
            end_at=end_at,
            user_id=user_id,
            entity_type=entity_type,
        )
        session_rows = (
            await self.db.execute(select(WorkSession).where(*session_conditions))
        ).scalars().all()
        for session in session_rows:
            duration = int(session.duration_seconds or 0)
            if session.user_id is not None:
                stats = user_stats[session.user_id]
                stats["active_crm_seconds"] += duration
                stats["last_active_at"] = _max_dt(stats["last_active_at"], session.last_seen_at)

            entity_key = _entity_key(session.entity_type, session.entity_id)
            estats = entity_stats[entity_key]
            estats["active_crm_seconds"] += duration
            estats["last_touched_at"] = _max_dt(estats["last_touched_at"], session.last_seen_at)

        activity_conditions = self._activity_filter_conditions(
            start_at=start_at,
            end_at=end_at,
            user_id=user_id,
            entity_type=entity_type,
        )
        activities = (
            await self.db.execute(select(Activity).where(*activity_conditions))
        ).scalars().all()
        for activity in activities:
            actor_id = activity.owner_id or activity.assigned_to_id
            if actor_id is not None:
                stats = user_stats[actor_id]
                if activity.activity_type == "call":
                    stats["calls"] += 1
                    stats["call_duration_minutes"] += int(activity.call_duration_minutes or 0)
                elif activity.activity_type == "email":
                    stats["emails"] += 1
                stats["last_active_at"] = _max_dt(stats["last_active_at"], activity.created_at)

            entity_key = _entity_key(activity.entity_type, activity.entity_id)
            estats = entity_stats[entity_key]
            estats["activity_count"] += 1
            estats["last_touched_at"] = _max_dt(estats["last_touched_at"], activity.created_at)

        entity_records = await self._load_entity_records(entity_stats)
        owner_names = await self._load_user_names(
            {
                record["owner_id"]
                for record in entity_records.values()
                if record.get("owner_id") is not None
            }
        )

        user_summaries = []
        for uid, user in users.items():
            stats = user_stats[uid]
            if (
                user_id is not None
                and uid != user_id
            ):
                continue
            if not user.is_active and not _user_stats_has_activity(stats):
                continue
            user_summaries.append({
                "user_id": uid,
                "user_name": user.full_name,
                "user_email": user.email,
                "role": user.role,
                "active_crm_seconds": stats["active_crm_seconds"],
                "audit_events": stats["audit_events"],
                "calls": stats["calls"],
                "call_duration_minutes": stats["call_duration_minutes"],
                "emails": stats["emails"],
                "proposals_touched": len(stats["proposals_touched"]),
                "opportunities_touched": len(stats["opportunities_touched"]),
                "last_active_at": stats["last_active_at"],
            })

        # Include orphaned/inactive users that no longer have a users row.
        for uid, stats in user_stats.items():
            if uid in users or (user_id is not None and uid != user_id):
                continue
            user_summaries.append({
                "user_id": uid,
                "user_name": f"Deleted user #{uid}",
                "user_email": None,
                "role": None,
                "active_crm_seconds": stats["active_crm_seconds"],
                "audit_events": stats["audit_events"],
                "calls": stats["calls"],
                "call_duration_minutes": stats["call_duration_minutes"],
                "emails": stats["emails"],
                "proposals_touched": len(stats["proposals_touched"]),
                "opportunities_touched": len(stats["opportunities_touched"]),
                "last_active_at": stats["last_active_at"],
            })

        user_summaries.sort(
            key=lambda row: (
                row["active_crm_seconds"],
                row["last_active_at"] or datetime.min.replace(tzinfo=UTC),
            ),
            reverse=True,
        )

        entity_summaries = []
        for key, stats in entity_stats.items():
            record = entity_records.get(key, {})
            owner_id = record.get("owner_id")
            last_touched_by_id = stats["last_touched_by_id"]
            entity_summaries.append({
                "entity_type": key[0],
                "entity_id": key[1],
                "label": record.get("label"),
                "owner_id": owner_id,
                "owner_name": owner_names.get(owner_id) if owner_id is not None else None,
                "active_crm_seconds": stats["active_crm_seconds"],
                "activity_count": stats["activity_count"],
                "audit_count": stats["audit_count"],
                "last_touched_at": stats["last_touched_at"],
                "last_touched_by_id": last_touched_by_id,
                "last_touched_by_name": (
                    users[last_touched_by_id].full_name
                    if last_touched_by_id in users
                    else None
                ),
            })

        entity_summaries.sort(
            key=lambda row: (
                row["last_touched_at"] or datetime.min.replace(tzinfo=UTC),
                row["active_crm_seconds"],
            ),
            reverse=True,
        )
        entity_summaries = entity_summaries[:entity_limit]

        totals = {
            "audit_events": len(audit_rows),
            "active_crm_seconds": sum(row["active_crm_seconds"] for row in user_summaries),
            "activities": len(activities),
            "calls": sum(row["calls"] for row in user_summaries),
            "emails": sum(row["emails"] for row in user_summaries),
            "security_events": len(security_events),
        }

        return {
            "start_at": start_at,
            "end_at": end_at,
            "totals": totals,
            "users": user_summaries,
            "entities": entity_summaries,
            "security": security_events,
        }

    async def get_work_sessions(
        self,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
        user_id: int | None = None,
        entity_type: str | None = None,
        entity_id: int | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """Return recent work sessions enriched with user names."""
        start_at, end_at = _date_range_to_datetimes(start_date, end_date)
        conditions = self._work_session_filter_conditions(
            start_at=start_at,
            end_at=end_at,
            user_id=user_id,
            entity_type=entity_type,
            entity_id=entity_id,
        )
        rows = (
            await self.db.execute(
                select(WorkSession, User.full_name.label("user_name"))
                .outerjoin(User, WorkSession.user_id == User.id)
                .where(*conditions)
                .order_by(WorkSession.last_seen_at.desc(), WorkSession.id.desc())
                .limit(limit)
            )
        ).all()
        return [_work_session_to_dict(session, user_name) for session, user_name in rows]

    def _audit_filter_conditions(
        self,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
        user_id: int | None = None,
        entity_type: str | None = None,
        entity_id: int | None = None,
        action: str | None = None,
        search: str | None = None,
    ) -> list[Any]:
        start_at, end_at = _date_range_to_datetimes(start_date, end_date)
        conditions: list[Any] = []
        if start_at is not None:
            conditions.append(AuditLog.timestamp >= start_at)
        if end_at is not None:
            conditions.append(AuditLog.timestamp <= end_at)
        if user_id is not None:
            conditions.append(AuditLog.user_id == user_id)
        if entity_type:
            conditions.append(AuditLog.entity_type.in_(entity_type_variants(entity_type)))
        if entity_id is not None:
            conditions.append(AuditLog.entity_id == entity_id)
        if action:
            conditions.append(AuditLog.action == action)
        if search and search.strip():
            pattern = f"%{search.strip()}%"
            conditions.append(or_(
                AuditLog.entity_type.ilike(pattern),
                AuditLog.action.ilike(pattern),
                AuditLog.ip_address.ilike(pattern),
                cast(AuditLog.entity_id, String).ilike(pattern),
                cast(AuditLog.changes, String).ilike(pattern),
                User.full_name.ilike(pattern),
                User.email.ilike(pattern),
            ))
        return conditions

    def _work_session_filter_conditions(
        self,
        *,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        user_id: int | None = None,
        entity_type: str | None = None,
        entity_id: int | None = None,
    ) -> list[Any]:
        conditions: list[Any] = []
        if start_at is not None:
            conditions.append(WorkSession.last_seen_at >= start_at)
        if end_at is not None:
            conditions.append(WorkSession.started_at <= end_at)
        if user_id is not None:
            conditions.append(WorkSession.user_id == user_id)
        if entity_type:
            conditions.append(WorkSession.entity_type.in_(entity_type_variants(entity_type)))
        if entity_id is not None:
            conditions.append(WorkSession.entity_id == entity_id)
        return conditions

    def _activity_filter_conditions(
        self,
        *,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        user_id: int | None = None,
        entity_type: str | None = None,
    ) -> list[Any]:
        conditions: list[Any] = []
        if start_at is not None:
            conditions.append(Activity.created_at >= start_at)
        if end_at is not None:
            conditions.append(Activity.created_at <= end_at)
        if user_id is not None:
            conditions.append(or_(Activity.owner_id == user_id, Activity.assigned_to_id == user_id))
        if entity_type:
            conditions.append(Activity.entity_type.in_(entity_type_variants(entity_type)))
        return conditions

    async def _load_users(self) -> dict[int, User]:
        result = await self.db.execute(select(User).order_by(User.full_name, User.id))
        return {user.id: user for user in result.scalars().all()}

    async def _load_user_names(self, user_ids: set[int]) -> dict[int, str]:
        if not user_ids:
            return {}
        result = await self.db.execute(
            select(User.id, User.full_name).where(User.id.in_(user_ids))
        )
        return dict(result.tuples().all())

    async def _load_entity_records(
        self,
        entity_stats: dict[tuple[str, int], dict],
    ) -> dict[tuple[str, int], dict]:
        ids_by_type: dict[str, set[int]] = defaultdict(set)
        for entity_type, entity_id in entity_stats:
            ids_by_type[canonical_singular(entity_type)].add(entity_id)

        records: dict[tuple[str, int], dict] = {}
        for singular, ids in ids_by_type.items():
            if singular == "contact":
                from src.contacts.models import Contact  # noqa: PLC0415
                rows = (await self.db.execute(
                    select(
                        Contact.id,
                        Contact.owner_id,
                        Contact.first_name,
                        Contact.last_name,
                        Contact.email,
                    ).where(Contact.id.in_(ids))
                )).all()
                for row in rows:
                    name = " ".join(part for part in [row.first_name, row.last_name] if part)
                    records[("contacts", row.id)] = {
                        "label": name or row.email or f"Contact #{row.id}",
                        "owner_id": row.owner_id,
                    }
            elif singular == "company":
                from src.companies.models import Company  # noqa: PLC0415
                rows = (await self.db.execute(
                    select(Company.id, Company.owner_id, Company.name).where(Company.id.in_(ids))
                )).all()
                for row in rows:
                    records[("companies", row.id)] = {
                        "label": row.name or f"Company #{row.id}",
                        "owner_id": row.owner_id,
                    }
            elif singular == "lead":
                from src.leads.models import Lead  # noqa: PLC0415
                rows = (await self.db.execute(
                    select(
                        Lead.id,
                        Lead.owner_id,
                        Lead.first_name,
                        Lead.last_name,
                        Lead.company_name,
                        Lead.email,
                    ).where(Lead.id.in_(ids))
                )).all()
                for row in rows:
                    name = " ".join(part for part in [row.first_name, row.last_name] if part)
                    records[("leads", row.id)] = {
                        "label": name or row.company_name or row.email or f"Lead #{row.id}",
                        "owner_id": row.owner_id,
                    }
            elif singular == "opportunity":
                from src.opportunities.models import Opportunity  # noqa: PLC0415
                rows = (await self.db.execute(
                    select(Opportunity.id, Opportunity.owner_id, Opportunity.name)
                    .where(Opportunity.id.in_(ids))
                )).all()
                for row in rows:
                    records[("opportunities", row.id)] = {
                        "label": row.name or f"Opportunity #{row.id}",
                        "owner_id": row.owner_id,
                    }
            elif singular == "proposal":
                from src.proposals.models import Proposal  # noqa: PLC0415
                rows = (await self.db.execute(
                    select(Proposal.id, Proposal.owner_id, Proposal.title)
                    .where(Proposal.id.in_(ids))
                )).all()
                for row in rows:
                    records[("proposals", row.id)] = {
                        "label": row.title or f"Proposal #{row.id}",
                        "owner_id": row.owner_id,
                    }
            elif singular == "payment":
                from src.payments.models import Payment  # noqa: PLC0415
                rows = (await self.db.execute(
                    select(Payment.id, Payment.owner_id).where(Payment.id.in_(ids))
                )).all()
                for row in rows:
                    records[("payments", row.id)] = {
                        "label": f"Payment #{row.id}",
                        "owner_id": row.owner_id,
                    }
            elif singular == "campaign":
                from src.campaigns.models import Campaign  # noqa: PLC0415
                rows = (await self.db.execute(
                    select(Campaign.id, Campaign.owner_id, Campaign.name)
                    .where(Campaign.id.in_(ids))
                )).all()
                for row in rows:
                    records[("campaigns", row.id)] = {
                        "label": row.name or f"Campaign #{row.id}",
                        "owner_id": row.owner_id,
                    }
            elif singular == "activity":
                rows = (await self.db.execute(
                    select(Activity.id, Activity.owner_id, Activity.subject)
                    .where(Activity.id.in_(ids))
                )).all()
                for row in rows:
                    records[("activities", row.id)] = {
                        "label": row.subject or f"Activity #{row.id}",
                        "owner_id": row.owner_id,
                    }

        for key in entity_stats:
            records.setdefault(key, {
                "label": f"{key[0]} #{key[1]}",
                "owner_id": None,
            })
        return records

    def _build_security_events(
        self,
        audit_rows: list[AuditLog],
        users: dict[int, User],
    ) -> list[dict]:
        events: list[dict] = []
        edit_counts: dict[int, dict[str, Any]] = defaultdict(lambda: {"count": 0, "latest": None})

        for log in audit_rows:
            user_name = users[log.user_id].full_name if log.user_id in users else None
            action = log.action.lower()
            singular = canonical_singular(log.entity_type)
            changes_text = str(log.changes or "").lower()

            if action in {"update", "import_merge"} and log.user_id is not None:
                bucket = edit_counts[log.user_id]
                bucket["count"] += 1
                bucket["latest"] = _max_dt(bucket["latest"], log.timestamp)

            if action == "delete":
                events.append({
                    "id": f"audit-{log.id}",
                    "severity": "high",
                    "category": "delete",
                    "description": f"{user_name or 'System'} deleted {log.entity_type} #{log.entity_id}",
                    "user_id": log.user_id,
                    "user_name": user_name,
                    "entity_type": log.entity_type,
                    "entity_id": log.entity_id,
                    "count": 1,
                    "created_at": log.timestamp,
                })
            elif "import" in action:
                events.append({
                    "id": f"audit-{log.id}",
                    "severity": "medium",
                    "category": "bulk_import",
                    "description": f"{user_name or 'System'} changed {log.entity_type} #{log.entity_id} via import",
                    "user_id": log.user_id,
                    "user_name": user_name,
                    "entity_type": log.entity_type,
                    "entity_id": log.entity_id,
                    "count": 1,
                    "created_at": log.timestamp,
                })
            elif action in {"share", "unshare"}:
                events.append({
                    "id": f"audit-{log.id}",
                    "severity": "medium",
                    "category": "sharing",
                    "description": f"{user_name or 'System'} changed sharing on {log.entity_type} #{log.entity_id}",
                    "user_id": log.user_id,
                    "user_name": user_name,
                    "entity_type": log.entity_type,
                    "entity_id": log.entity_id,
                    "count": 1,
                    "created_at": log.timestamp,
                })
            elif singular in {"user", "role"} or "permission" in changes_text or "role" in changes_text:
                events.append({
                    "id": f"audit-{log.id}",
                    "severity": "high",
                    "category": "permission",
                    "description": f"{user_name or 'System'} changed permissions or roles",
                    "user_id": log.user_id,
                    "user_name": user_name,
                    "entity_type": log.entity_type,
                    "entity_id": log.entity_id,
                    "count": 1,
                    "created_at": log.timestamp,
                })

        for uid, bucket in edit_counts.items():
            if bucket["count"] < 25:
                continue
            user_name = users[uid].full_name if uid in users else f"User #{uid}"
            events.append({
                "id": f"volume-{uid}",
                "severity": "medium",
                "category": "high_volume_edits",
                "description": f"{user_name} made {bucket['count']} edits in the selected period",
                "user_id": uid,
                "user_name": user_name,
                "entity_type": None,
                "entity_id": None,
                "count": bucket["count"],
                "created_at": bucket["latest"] or datetime.now(UTC),
            })

        events.sort(key=lambda item: item["created_at"], reverse=True)
        return events


class WorkSessionService:
    """Service for coarse, privacy-preserving active CRM time tracking."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def heartbeat(
        self,
        *,
        user_id: int,
        entity_type: str,
        entity_id: int,
        source: str = "detail_page",
        metadata: dict | None = None,
        now: datetime | None = None,
    ) -> WorkSession:
        """Merge a heartbeat into the current active session or start a new one."""
        seen_at = _ensure_aware(now or datetime.now(UTC))
        normalized_entity_type = canonical_plural(entity_type)

        result = await self.db.execute(
            select(WorkSession)
            .where(
                WorkSession.user_id == user_id,
                WorkSession.entity_type == normalized_entity_type,
                WorkSession.entity_id == entity_id,
                WorkSession.source == (source or "detail_page"),
                WorkSession.ended_at.is_(None),
            )
            .order_by(WorkSession.last_seen_at.desc(), WorkSession.id.desc())
            .limit(1)
        )
        session = result.scalar_one_or_none()

        if session is not None:
            last_seen = _ensure_aware(session.last_seen_at)
            gap_seconds = (seen_at - last_seen).total_seconds()
            if 0 <= gap_seconds <= WORK_SESSION_IDLE_TIMEOUT_SECONDS:
                session.last_seen_at = seen_at
                session.duration_seconds = _duration_seconds(session.started_at, seen_at)
                if metadata is not None:
                    session.metadata_ = metadata
                await self.db.flush()
                await self.db.refresh(session)
                return session

            session.ended_at = last_seen
            session.duration_seconds = _duration_seconds(session.started_at, last_seen)

        new_session = WorkSession(
            user_id=user_id,
            entity_type=normalized_entity_type,
            entity_id=entity_id,
            started_at=seen_at,
            last_seen_at=seen_at,
            duration_seconds=0,
            source=source or "detail_page",
            metadata_=metadata,
        )
        self.db.add(new_session)
        try:
            await self.db.flush()
        except IntegrityError:
            # The partial unique index in migration 044 prevents two open
            # rows per (user, entity, source). If a concurrent heartbeat
            # won the race and inserted first, roll back this INSERT and
            # update its row instead so we converge on one open session.
            await self.db.rollback()
            retry = await self.db.execute(
                select(WorkSession)
                .where(
                    WorkSession.user_id == user_id,
                    WorkSession.entity_type == normalized_entity_type,
                    WorkSession.entity_id == entity_id,
                    WorkSession.source == (source or "detail_page"),
                    WorkSession.ended_at.is_(None),
                )
                .limit(1)
            )
            existing = retry.scalar_one_or_none()
            if existing is None:
                raise
            existing.last_seen_at = seen_at
            existing.duration_seconds = _duration_seconds(existing.started_at, seen_at)
            if metadata is not None:
                existing.metadata_ = metadata
            await self.db.flush()
            await self.db.refresh(existing)
            return existing
        await self.db.refresh(new_session)
        return new_session


def _date_range_to_datetimes(
    start_date: date | None,
    end_date: date | None,
) -> tuple[datetime | None, datetime | None]:
    start_at = datetime.combine(start_date, time.min, tzinfo=UTC) if start_date else None
    end_at = datetime.combine(end_date, time.max, tzinfo=UTC) if end_date else None
    return start_at, end_at


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _duration_seconds(started_at: datetime, ended_at: datetime) -> int:
    return max(0, int((_ensure_aware(ended_at) - _ensure_aware(started_at)).total_seconds()))


def _max_dt(current: datetime | None, candidate: datetime | None) -> datetime | None:
    if candidate is None:
        return current
    if current is None:
        return candidate
    return candidate if _ensure_aware(candidate) > _ensure_aware(current) else current


def _entity_key(entity_type: str, entity_id: int) -> tuple[str, int]:
    return canonical_plural(entity_type), entity_id


def _new_user_stats() -> defaultdict[int, dict[str, Any]]:
    return defaultdict(lambda: {
        "active_crm_seconds": 0,
        "audit_events": 0,
        "calls": 0,
        "call_duration_minutes": 0,
        "emails": 0,
        "proposals_touched": set(),
        "opportunities_touched": set(),
        "last_active_at": None,
    })


def _new_entity_stats() -> defaultdict[tuple[str, int], dict[str, Any]]:
    return defaultdict(lambda: {
        "active_crm_seconds": 0,
        "activity_count": 0,
        "audit_count": 0,
        "last_touched_at": None,
        "last_touched_by_id": None,
    })


def _user_stats_has_activity(stats: dict[str, Any]) -> bool:
    return bool(
        stats["active_crm_seconds"]
        or stats["audit_events"]
        or stats["calls"]
        or stats["emails"]
        or stats["last_active_at"]
    )


def _work_session_to_dict(session: WorkSession, user_name: str | None = None) -> dict:
    return {
        "id": session.id,
        "user_id": session.user_id,
        "user_name": user_name,
        "entity_type": session.entity_type,
        "entity_id": session.entity_id,
        "started_at": session.started_at,
        "last_seen_at": session.last_seen_at,
        "ended_at": session.ended_at,
        "duration_seconds": session.duration_seconds,
        "source": session.source,
        "metadata": session.metadata_,
    }


def detect_changes(old_data: dict, new_data: dict) -> list[dict]:
    """Compare old and new data dicts and return list of changed fields.

    Args:
        old_data: Dictionary of old field values
        new_data: Dictionary of new field values (only fields being updated)

    Returns:
        List of dicts with field, old_value, new_value for each changed field
    """
    changes = []
    for field, new_value in new_data.items():
        old_value = old_data.get(field)
        # Convert to comparable strings for comparison
        old_str = _to_comparable(old_value)
        new_str = _to_comparable(new_value)
        if old_str != new_str:
            changes.append({
                "field": field,
                "old_value": _serialize(old_value),
                "new_value": _serialize(new_value),
            })
    return changes


def _to_comparable(value: Any) -> str:
    """Convert a value to a comparable string representation."""
    if value is None:
        return ""
    return str(value)


def _serialize(value: Any) -> Any:
    """Serialize a value for JSON storage."""
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value) if not isinstance(value, str | int | float | bool) else value
