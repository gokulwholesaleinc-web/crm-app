"""Duplicate detection and merge service for CRM entities."""

import logging
import re
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.activities.models import Activity
from src.companies.models import Company
from src.contacts.models import Contact
from src.core.models import EntityTag, Note
from src.leads.models import Lead

logger = logging.getLogger(__name__)


# Company suffixes to strip for normalization
COMPANY_SUFFIXES = re.compile(
    r"\b(inc|incorporated|llc|ltd|limited|corp|corporation|co|company|group|holdings|plc|gmbh|sa|ag)\b\.?",
    re.IGNORECASE,
)


def normalize_name(name: str) -> str:
    """Normalize a name for comparison: lowercase, strip extra whitespace."""
    return " ".join(name.lower().split())


def normalize_company_name(name: str) -> str:
    """Normalize company name: lowercase, strip suffixes and extra whitespace."""
    normalized = name.lower().strip()
    normalized = COMPANY_SUFFIXES.sub("", normalized)
    normalized = re.sub(r"[.,]", "", normalized)
    return " ".join(normalized.split())


def normalize_phone(phone: str) -> str:
    """Normalize phone number by stripping non-digit characters."""
    return re.sub(r"\D", "", phone)


def names_are_similar(name1: str, name2: str) -> bool:
    """Check if two names are similar using simple normalization comparison."""
    n1 = normalize_name(name1)
    n2 = normalize_name(name2)
    return n1 == n2


ALLOWED_CLUSTER_ENTITIES: tuple[str, ...] = ("contacts", "companies", "leads")
ALLOWED_CLUSTER_KEYS_BY_ENTITY: dict[str, tuple[str, ...]] = {
    "contacts": ("email", "phone", "name"),
    "companies": ("email", "phone", "name"),
    "leads": ("email", "phone"),
}


def _classify_merge_failure(reason: str) -> str:
    """Map a free-form ``ValueError`` text into a coarse code the UI can branch on.

    ``_load_merge_pair`` produces three distinct messages:
    * ``"Cannot merge a record into itself"`` → ``self_merge``
    * ``"Primary <model> <id> not found"`` → ``not_found_primary``
    * ``"Secondary <model> <id> not found"`` → ``stale_cluster`` (the row
      vanished between cluster render and merge — operator should refresh)

    Anything else falls through to ``other`` so a future reason still
    appears in the response without breaking the schema.
    """
    lower = reason.lower()
    if "cannot merge a record into itself" in lower:
        return "self_merge"
    if "secondary" in lower and "not found" in lower:
        return "stale_cluster"
    if "primary" in lower and "not found" in lower:
        return "not_found_primary"
    return "other"


def _cluster_key_for(entity: Any, key: str) -> str | None:
    """Compute the bucket key for grouping. ``None`` means the row is not
    a candidate (no value at all)."""
    if key == "email":
        email = getattr(entity, "email", None)
        return email.lower().strip() if isinstance(email, str) and email.strip() else None
    if key == "phone":
        phone = getattr(entity, "phone", None)
        normalized = normalize_phone(phone) if isinstance(phone, str) else ""
        return normalized or None
    if key == "name":
        # For companies use the normalized name (strips suffixes); for
        # contacts/leads collapse first+last lowercased.
        company_name = getattr(entity, "name", None)
        if isinstance(company_name, str) and company_name.strip():
            return normalize_company_name(company_name)
        first = (getattr(entity, "first_name", "") or "").strip().lower()
        last = (getattr(entity, "last_name", "") or "").strip().lower()
        if first or last:
            return f"{first} {last}".strip()
        return None
    return None


class DedupService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def find_duplicate_contacts(
        self,
        email: str | None = None,
        phone: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        exclude_id: int | None = None,
    ) -> list[Contact]:
        """Find potential duplicate contacts by email, phone, or name."""
        conditions = []

        if email:
            conditions.append(func.lower(Contact.email) == email.lower())

        if phone:
            normalized = normalize_phone(phone)
            if normalized:
                conditions.append(Contact.phone.isnot(None))

        if first_name and last_name:
            conditions.append(
                (func.lower(Contact.first_name) == first_name.lower())
                & (func.lower(Contact.last_name) == last_name.lower())
            )

        if not conditions:
            return []

        query = select(Contact).where(or_(*conditions))
        if exclude_id:
            query = query.where(Contact.id != exclude_id)

        result = await self.db.execute(query)
        candidates = list(result.scalars().all())

        # Post-filter phone matches by normalized comparison
        if phone:
            normalized_input = normalize_phone(phone)
            filtered = []
            for c in candidates:
                # Already matched by email or name
                match_by_email = email and c.email and c.email.lower() == email.lower()
                match_by_name = (
                    first_name and last_name
                    and c.first_name.lower() == first_name.lower()
                    and c.last_name.lower() == last_name.lower()
                )
                match_by_phone = c.phone and normalize_phone(c.phone) == normalized_input
                if match_by_email or match_by_name or match_by_phone:
                    filtered.append(c)
            return filtered

        return candidates

    async def find_duplicate_companies(
        self,
        name: str | None = None,
        exclude_id: int | None = None,
    ) -> list[Company]:
        """Find potential duplicate companies by normalized name."""
        if not name:
            return []

        # Fetch all companies and compare normalized names
        query = select(Company)
        if exclude_id:
            query = query.where(Company.id != exclude_id)

        result = await self.db.execute(query)
        companies = result.scalars().all()

        target_normalized = normalize_company_name(name)
        return [
            c for c in companies
            if normalize_company_name(c.name) == target_normalized
        ]

    async def find_duplicate_leads(
        self,
        email: str | None = None,
        phone: str | None = None,
        exclude_id: int | None = None,
    ) -> list[Lead]:
        """Find potential duplicate leads by exact email or phone match."""
        conditions = []

        if email:
            conditions.append(func.lower(Lead.email) == email.lower())

        if phone:
            conditions.append(Lead.phone.isnot(None))

        if not conditions:
            return []

        query = select(Lead).where(or_(*conditions))
        if exclude_id:
            query = query.where(Lead.id != exclude_id)

        result = await self.db.execute(query)
        candidates = list(result.scalars().all())

        if phone:
            normalized_input = normalize_phone(phone)
            filtered = []
            for l in candidates:
                match_by_email = email and l.email and l.email.lower() == email.lower()
                match_by_phone = l.phone and normalize_phone(l.phone) == normalized_input
                if match_by_email or match_by_phone:
                    filtered.append(l)
            return filtered

        return candidates

    async def check_duplicates(
        self,
        entity_type: str,
        data: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Check for duplicates before creation. Returns list of potential matches."""
        duplicates = []

        if entity_type == "contacts":
            matches = await self.find_duplicate_contacts(
                email=data.get("email"),
                phone=data.get("phone"),
                first_name=data.get("first_name"),
                last_name=data.get("last_name"),
            )
            for m in matches:
                duplicates.append({
                    "id": m.id,
                    "entity_type": "contacts",
                    "display_name": f"{m.first_name} {m.last_name}",
                    "email": m.email,
                    "phone": m.phone,
                    "match_reason": self._contact_match_reason(m, data),
                })

        elif entity_type == "companies":
            matches = await self.find_duplicate_companies(name=data.get("name"))
            for m in matches:
                duplicates.append({
                    "id": m.id,
                    "entity_type": "companies",
                    "display_name": m.name,
                    "email": m.email,
                    "phone": m.phone,
                    "match_reason": "Company name match",
                })

        elif entity_type == "leads":
            matches = await self.find_duplicate_leads(
                email=data.get("email"),
                phone=data.get("phone"),
            )
            for m in matches:
                duplicates.append({
                    "id": m.id,
                    "entity_type": "leads",
                    "display_name": f"{m.first_name} {m.last_name}",
                    "email": m.email,
                    "phone": m.phone,
                    "match_reason": self._lead_match_reason(m, data),
                })

        return duplicates

    def _contact_match_reason(self, contact: Contact, data: dict[str, Any]) -> str:
        reasons = []
        if data.get("email") and contact.email and contact.email.lower() == data["email"].lower():
            reasons.append("Email match")
        if data.get("phone") and contact.phone and normalize_phone(contact.phone) == normalize_phone(data["phone"]):
            reasons.append("Phone match")
        if (
            data.get("first_name") and data.get("last_name")
            and contact.first_name.lower() == data["first_name"].lower()
            and contact.last_name.lower() == data["last_name"].lower()
        ):
            reasons.append("Name match")
        return ", ".join(reasons) if reasons else "Potential match"

    def _lead_match_reason(self, lead: Lead, data: dict[str, Any]) -> str:
        reasons = []
        if data.get("email") and lead.email and lead.email.lower() == data["email"].lower():
            reasons.append("Email match")
        if data.get("phone") and lead.phone and normalize_phone(lead.phone) == normalize_phone(data["phone"]):
            reasons.append("Phone match")
        return ", ".join(reasons) if reasons else "Potential match"

    async def merge_contacts(
        self,
        primary_id: int,
        secondary_id: int,
        user_id: int | None = None,
    ) -> Contact:
        """Merge ``secondary`` contact into ``primary``.

        Transfers every FK pointing at the secondary contact (quotes,
        proposals, opportunities, contracts, sequences, stripe customers,
        payments, inbound emails) plus the polymorphic links (activities,
        notes, entity tags, email queue, audit, ai feedback). Then
        SOFT-DELETES the secondary:

        * ``status = "merged"``
        * ``deleted_at`` set to now
        * ``merged_into_id`` points at the primary
        * ``email`` is prefixed so the unique constraint releases the
          original address

        An ``AuditLog`` entry records who performed the merge.

        Never hard-deletes — per project rule
        ``feedback_delete_sales_only.md`` contacts anchor AR ledger and
        invoice history that must survive the merge.
        """
        primary, secondary = await self._load_merge_pair(Contact, primary_id, secondary_id)

        await self._transfer_contact_fks(secondary_id, primary_id)
        await self._transfer_entity_links("contacts", secondary_id, primary_id)

        self._soft_delete_merged(secondary, primary_id)

        await self._log_merge_audit(
            entity_type="contact",
            primary_id=primary_id,
            secondary_id=secondary_id,
            user_id=user_id,
        )

        await self.db.flush()
        await self.db.refresh(primary)
        return primary

    async def merge_companies(
        self,
        primary_id: int,
        secondary_id: int,
        user_id: int | None = None,
    ) -> Company:
        """Merge ``secondary`` company into ``primary``.

        Repoints every child FK (contacts, opportunities, quotes,
        proposals, contracts, Stripe customers) + polymorphic links +
        soft-deletes the secondary with ``status="merged"`` and a
        ``merged_into_id`` forwarding pointer. Writes an audit log entry.
        """
        primary, secondary = await self._load_merge_pair(Company, primary_id, secondary_id)

        await self._transfer_company_fks(secondary_id, primary_id)
        await self._transfer_entity_links("companies", secondary_id, primary_id)

        secondary.status = "merged"
        secondary.merged_into_id = primary_id

        await self._log_merge_audit(
            entity_type="company",
            primary_id=primary_id,
            secondary_id=secondary_id,
            user_id=user_id,
        )

        await self.db.flush()
        await self.db.refresh(primary)
        return primary

    async def merge_leads(
        self,
        primary_id: int,
        secondary_id: int,
        user_id: int | None = None,
    ) -> Lead:
        """Merge ``secondary`` lead into ``primary``.

        Soft-deletes the secondary lead (``status="merged"`` +
        ``merged_into_id``) after transferring polymorphic links. Writes
        an audit log entry. Leads currently have fewer direct FKs than
        contacts/companies, so no table-specific repoint pass is needed
        beyond the polymorphic link transfer.
        """
        primary, secondary = await self._load_merge_pair(Lead, primary_id, secondary_id)

        await self._transfer_entity_links("leads", secondary_id, primary_id)

        secondary.status = "merged"
        secondary.merged_into_id = primary_id

        await self._log_merge_audit(
            entity_type="lead",
            primary_id=primary_id,
            secondary_id=secondary_id,
            user_id=user_id,
        )

        await self.db.flush()
        await self.db.refresh(primary)
        return primary

    async def _load_merge_pair(self, model, primary_id: int, secondary_id: int):
        """Fetch the primary and secondary rows for a merge operation.

        Raises ``ValueError`` with a clear message when either is missing
        or when the caller accidentally passes the same id twice.
        """
        if primary_id == secondary_id:
            raise ValueError("Cannot merge a record into itself")

        result = await self.db.execute(select(model).where(model.id == primary_id))
        primary = result.scalar_one_or_none()
        if not primary:
            raise ValueError(f"Primary {model.__tablename__[:-1]} {primary_id} not found")

        result = await self.db.execute(select(model).where(model.id == secondary_id))
        secondary = result.scalar_one_or_none()
        if not secondary:
            raise ValueError(f"Secondary {model.__tablename__[:-1]} {secondary_id} not found")

        return primary, secondary

    def _soft_delete_merged(self, contact: Contact, primary_id: int) -> None:
        """Mark a merged-away contact as soft-deleted and free its email slot."""
        contact.status = "merged"
        contact.deleted_at = datetime.now(UTC)
        contact.merged_into_id = primary_id
        if contact.email and not contact.email.startswith(("archived-", "merged-")):
            prefix = f"merged-{contact.id}-"
            contact.email = (prefix + contact.email)[:255]

    async def _transfer_contact_fks(self, from_id: int, to_id: int) -> None:
        """Repoint every direct FK column that references ``contacts.id``.

        Discovered from the models that carry ``ForeignKey("contacts.id")``:
        quotes, proposals, opportunities, contracts, payments (StripeCustomer
        has its own contact_id), sequences/enrollments. Each one gets an
        UPDATE that moves the secondary's rows onto the primary. Models we
        do not touch cascade via SET NULL on the original FK, which would
        break the merge, so this list must be kept in sync with the
        ``contacts.id`` FK set across the codebase.
        """
        from src.contracts.models import Contract
        from src.opportunities.models import Opportunity
        from src.payments.models import StripeCustomer
        from src.proposals.models import Proposal
        from src.quotes.models import Quote
        from src.sequences.models import SequenceEnrollment

        tables_with_contact_fk = [
            (Quote, Quote.contact_id),
            (Proposal, Proposal.contact_id),
            (Opportunity, Opportunity.contact_id),
            (Contract, Contract.contact_id),
            (StripeCustomer, StripeCustomer.contact_id),
            (SequenceEnrollment, SequenceEnrollment.contact_id),
        ]

        for model, column in tables_with_contact_fk:
            await self.db.execute(
                update(model).where(column == from_id).values(contact_id=to_id)
            )

        # Lead.converted_contact_id is a historical marker — rewrite so
        # the converted-from pointer follows the surviving contact.
        await self.db.execute(
            update(Lead)
            .where(Lead.converted_contact_id == from_id)
            .values(converted_contact_id=to_id)
        )

    async def _transfer_company_fks(self, from_id: int, to_id: int) -> None:
        """Repoint every direct FK column that references ``companies.id``."""
        from src.contracts.models import Contract
        from src.opportunities.models import Opportunity
        from src.payments.models import StripeCustomer
        from src.proposals.models import Proposal
        from src.quotes.models import Quote

        # Contacts: move them to the surviving company instead of deleting.
        await self.db.execute(
            update(Contact).where(Contact.company_id == from_id).values(company_id=to_id)
        )

        tables_with_company_fk = [
            (Quote, Quote.company_id),
            (Proposal, Proposal.company_id),
            (Opportunity, Opportunity.company_id),
            (Contract, Contract.company_id),
            (StripeCustomer, StripeCustomer.company_id),
        ]
        for model, column in tables_with_company_fk:
            await self.db.execute(
                update(model).where(column == from_id).values(company_id=to_id)
            )

    async def _log_merge_audit(
        self,
        *,
        entity_type: str,
        primary_id: int,
        secondary_id: int,
        user_id: int | None,
    ) -> None:
        """Write an audit log entry describing the merge.

        Uses the same ``AuditService`` that router-level delete/update
        events use so merges show up alongside ordinary history on the
        contact detail page.
        """
        try:
            from src.audit.service import AuditService
            service = AuditService(self.db)
            await service.log_change(
                entity_type=entity_type,
                entity_id=primary_id,
                user_id=user_id,
                action="merge",
                changes=[
                    {
                        "field": "merged_from_id",
                        "old": None,
                        "new": secondary_id,
                    }
                ],
            )
        except Exception as exc:  # pragma: no cover - defensive
            # An audit failure must not roll back a correct merge.
            logger.warning("Failed to audit %s merge %s→%s: %s", entity_type, secondary_id, primary_id, exc)

    async def _transfer_entity_links(
        self,
        entity_type: str,
        from_id: int,
        to_id: int,
    ) -> None:
        """Transfer polymorphic links from secondary to primary.

        Covers every table that keys on ``(entity_type, entity_id)``:
        activities, notes, inbound/outbound emails, attachments,
        comments, notifications, and entity tags. Missing any of these
        is user-visible data loss — e.g. a contract uploaded to the
        merged-away contact would become unreachable.

        Tag rows that would collide with an existing ``(entity_id,
        tag_id)`` pair on the primary are deleted instead of transferred
        to avoid unique-constraint violations.
        """
        from src.attachments.models import Attachment
        from src.comments.models import Comment
        from src.email.models import EmailQueue, InboundEmail
        from src.notifications.models import Notification

        polymorphic_models = (
            Activity,
            Note,
            EmailQueue,
            InboundEmail,
            Attachment,
            Comment,
            Notification,
        )
        for model in polymorphic_models:
            await self.db.execute(
                update(model)
                .where(model.entity_type == entity_type)
                .where(model.entity_id == from_id)
                .values(entity_id=to_id)
            )

        # Transfer tags — avoid (entity_id, tag_id) collisions on the primary.
        existing_tags_result = await self.db.execute(
            select(EntityTag.tag_id)
            .where(EntityTag.entity_type == entity_type)
            .where(EntityTag.entity_id == to_id)
        )
        existing_tag_ids = set(existing_tags_result.scalars().all())

        secondary_tags_result = await self.db.execute(
            select(EntityTag)
            .where(EntityTag.entity_type == entity_type)
            .where(EntityTag.entity_id == from_id)
        )
        for et in secondary_tags_result.scalars().all():
            if et.tag_id in existing_tag_ids:
                await self.db.delete(et)
            else:
                et.entity_id = to_id

        await self.db.flush()

    # ------------------------------------------------------------------
    # Cluster discovery — used by /api/dedup/clusters (admin tool)
    # ------------------------------------------------------------------

    async def find_duplicate_clusters(
        self,
        entity_type: str,
        key: str,
    ) -> dict[str, Any]:
        """Group live rows of an entity by the chosen match key.

        Returns ``{"clusters": [...], "skipped_no_key": int}`` — each
        cluster dict has the matched key value, the member count, and
        the list of members. Each member carries id, display label,
        ``created_at``, ``last_activity_at`` (max(activities.created_at)),
        and the polymorphic activity count — enough for the admin UI to
        pick the "winner" without round-tripping per row.

        ``skipped_no_key`` is the count of live rows that lacked a value
        for the chosen match key (e.g. a contact with no phone when
        ``key="phone"``). Surfacing it tells the operator how much of
        the dataset the current match key actually evaluates — a small
        cluster count next to a big skipped count is usually a hint to
        switch keys.

        Soft-deleted and already-merged rows are excluded so the operator
        only sees clusters they can actually act on.

        Today this reads the full live table for the entity into memory.
        TODO: paginate or stream when a tenant grows past ~25k rows; the
        normalize-in-Python branch (name match) is the bottleneck.
        """
        if entity_type not in ALLOWED_CLUSTER_ENTITIES:
            raise ValueError(
                f"Invalid entity_type '{entity_type}'. Allowed: {', '.join(ALLOWED_CLUSTER_ENTITIES)}"
            )
        allowed_keys = ALLOWED_CLUSTER_KEYS_BY_ENTITY[entity_type]
        if key not in allowed_keys:
            raise ValueError(
                f"Invalid key '{key}' for {entity_type}. Allowed: {', '.join(allowed_keys)}"
            )

        model = {"contacts": Contact, "companies": Company, "leads": Lead}[entity_type]

        query = select(model)
        if hasattr(model, "deleted_at"):
            query = query.where(model.deleted_at.is_(None))
        if hasattr(model, "merged_into_id"):
            query = query.where(model.merged_into_id.is_(None))
        result = await self.db.execute(query)
        rows = list(result.scalars().all())

        # Bucket rows by key. One pass; rows with no value land in
        # `skipped_no_key` so the UI can surface "412 records had no
        # phone, switch to email if you expected coverage there".
        buckets: dict[str, list[Any]] = {}
        skipped_no_key = 0
        for row in rows:
            bucket_key = _cluster_key_for(row, key)
            if bucket_key is None:
                skipped_no_key += 1
                continue
            buckets.setdefault(bucket_key, []).append(row)

        # Only buckets with >= 2 members are actual duplicate clusters.
        dup_ids: list[int] = [r.id for members in buckets.values() if len(members) >= 2 for r in members]
        try:
            activity_meta = await self._activity_meta_for(entity_type, dup_ids)
        except Exception:
            # Bubble the underlying error after capturing context — the
            # cluster meta lookup failing leaves us unable to render a
            # trustworthy "winner" recommendation, so we'd rather fail
            # loudly than serve zeros that look like real data.
            logger.exception(
                "dedup cluster meta lookup failed",
                extra={"entity_type": entity_type, "dup_id_count": len(dup_ids)},
            )
            raise

        clusters: list[dict[str, Any]] = []
        for bucket_key, members in buckets.items():
            if len(members) < 2:
                continue
            cluster_members = [
                self._render_cluster_member(entity_type, m, activity_meta)
                for m in members
            ]
            # Sort members so the most-recently-active appears first — the
            # operator usually wants to keep the most-touched record as
            # the winner.
            cluster_members.sort(
                key=lambda m: (m.get("last_activity_at") or m.get("created_at") or ""),
                reverse=True,
            )
            clusters.append({
                "key": key,
                "key_value": bucket_key,
                "member_count": len(cluster_members),
                "members": cluster_members,
            })

        # Stable order: biggest clusters first; ties broken by key_value
        # so a deterministic order shows up in tests and the UI.
        clusters.sort(key=lambda c: (-c["member_count"], c["key_value"]))
        return {"clusters": clusters, "skipped_no_key": skipped_no_key}

    async def _activity_meta_for(
        self,
        entity_type: str,
        entity_ids: list[int],
    ) -> dict[int, dict[str, Any]]:
        """Fetch (count, max(created_at)) per entity_id in a single query."""
        if not entity_ids:
            return {}
        result = await self.db.execute(
            select(
                Activity.entity_id,
                func.count(Activity.id).label("activity_count"),
                func.max(Activity.created_at).label("last_activity_at"),
            )
            .where(Activity.entity_type == entity_type)
            .where(Activity.entity_id.in_(entity_ids))
            .group_by(Activity.entity_id)
        )
        meta: dict[int, dict[str, Any]] = {}
        for row in result.all():
            meta[row.entity_id] = {
                "activity_count": int(row.activity_count or 0),
                "last_activity_at": row.last_activity_at,
            }
        return meta

    @staticmethod
    def _render_cluster_member(
        entity_type: str,
        entity: Any,
        activity_meta: dict[int, dict[str, Any]],
    ) -> dict[str, Any]:
        info = activity_meta.get(entity.id, {})
        last_activity = info.get("last_activity_at")
        created_at = getattr(entity, "created_at", None)

        if entity_type == "companies":
            label = getattr(entity, "name", None) or "(no name)"
        else:
            first = (getattr(entity, "first_name", "") or "").strip()
            last = (getattr(entity, "last_name", "") or "").strip()
            label = f"{first} {last}".strip() or "(no name)"

        return {
            "id": entity.id,
            "label": label,
            "email": getattr(entity, "email", None),
            "phone": getattr(entity, "phone", None),
            "company_id": getattr(entity, "company_id", None),
            "owner_id": getattr(entity, "owner_id", None),
            "created_at": created_at.isoformat() if created_at else None,
            "last_activity_at": last_activity.isoformat() if last_activity else None,
            "activity_count": info.get("activity_count", 0),
        }

    # ------------------------------------------------------------------
    # Bulk merge for the admin cluster tool
    # ------------------------------------------------------------------

    async def merge_cluster(
        self,
        *,
        entity_type: str,
        winner_id: int,
        loser_ids: list[int],
        user_id: int | None = None,
    ) -> dict[str, Any]:
        """Merge every loser_id into the winner_id for the chosen entity.

        Delegates to the existing single-pair merge primitives so the
        FK fanout, polymorphic link transfer, tag dedup, audit log, and
        soft-delete behavior all stay in one place. Returns a summary
        dict shaped for the API response.

        Per-loser ``ValueError`` (bad id, already-merged tombstone) is
        caught and recorded in ``failures`` with a coarse ``reason_code``
        so the UI can distinguish "stale cluster, refresh" from "bad
        input". SQLAlchemy errors deliberately propagate — they signal
        session state that the caller cannot reason about, and
        ``get_db`` will roll the whole request transaction back including
        any earlier successful pair-merges.
        """
        if entity_type not in ALLOWED_CLUSTER_ENTITIES:
            raise ValueError(
                f"Invalid entity_type '{entity_type}'. Allowed: {', '.join(ALLOWED_CLUSTER_ENTITIES)}"
            )
        if winner_id in loser_ids:
            raise ValueError("winner_id must not appear in loser_ids")
        if not loser_ids:
            raise ValueError("loser_ids must contain at least one id")

        merge_fn = {
            "contacts": self.merge_contacts,
            "companies": self.merge_companies,
            "leads": self.merge_leads,
        }[entity_type]

        merged: list[int] = []
        failures: list[dict[str, Any]] = []
        for loser_id in loser_ids:
            try:
                await merge_fn(winner_id, loser_id, user_id=user_id)
                merged.append(loser_id)
            except ValueError as exc:
                reason_str = str(exc)
                reason_code = _classify_merge_failure(reason_str)
                logger.warning(
                    "dedup cluster merge failed for one loser",
                    extra={
                        "entity_type": entity_type,
                        "winner_id": winner_id,
                        "loser_id": loser_id,
                        "user_id": user_id,
                        "reason_code": reason_code,
                        "reason": reason_str,
                    },
                )
                failures.append({
                    "id": loser_id,
                    "reason": reason_str,
                    "reason_code": reason_code,
                })

        return {
            "winner_id": winner_id,
            "merged_ids": merged,
            "failures": failures,
        }
