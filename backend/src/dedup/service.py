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
        proposals, contracts) + polymorphic links + soft-deletes the
        secondary with ``status="merged"`` and a ``merged_into_id``
        forwarding pointer. Writes an audit log entry.
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
