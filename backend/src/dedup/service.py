"""Duplicate detection and merge service for CRM entities."""

import re
from typing import List, Dict, Any, Optional
from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.contacts.models import Contact
from src.companies.models import Company
from src.leads.models import Lead
from src.activities.models import Activity
from src.core.models import Note, EntityTag


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
        email: Optional[str] = None,
        phone: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        exclude_id: Optional[int] = None,
    ) -> List[Contact]:
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
        name: Optional[str] = None,
        exclude_id: Optional[int] = None,
    ) -> List[Company]:
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
        email: Optional[str] = None,
        phone: Optional[str] = None,
        exclude_id: Optional[int] = None,
    ) -> List[Lead]:
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
        data: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
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

    def _contact_match_reason(self, contact: Contact, data: Dict[str, Any]) -> str:
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

    def _lead_match_reason(self, lead: Lead, data: Dict[str, Any]) -> str:
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
    ) -> Contact:
        """Merge secondary contact into primary. Transfers activities, notes, and tags."""
        primary = await self.db.execute(
            select(Contact).where(Contact.id == primary_id)
        )
        primary = primary.scalar_one_or_none()
        if not primary:
            raise ValueError(f"Primary contact {primary_id} not found")

        secondary = await self.db.execute(
            select(Contact).where(Contact.id == secondary_id)
        )
        secondary = secondary.scalar_one_or_none()
        if not secondary:
            raise ValueError(f"Secondary contact {secondary_id} not found")

        # Transfer activities
        await self._transfer_entity_links("contacts", secondary_id, primary_id)

        # Delete secondary
        await self.db.delete(secondary)
        await self.db.flush()
        await self.db.refresh(primary)
        return primary

    async def merge_companies(
        self,
        primary_id: int,
        secondary_id: int,
    ) -> Company:
        """Merge secondary company into primary. Transfers activities, notes, tags, and contacts."""
        primary = await self.db.execute(
            select(Company).where(Company.id == primary_id)
        )
        primary = primary.scalar_one_or_none()
        if not primary:
            raise ValueError(f"Primary company {primary_id} not found")

        secondary = await self.db.execute(
            select(Company).where(Company.id == secondary_id)
        )
        secondary = secondary.scalar_one_or_none()
        if not secondary:
            raise ValueError(f"Secondary company {secondary_id} not found")

        # Transfer contacts from secondary to primary
        contacts_result = await self.db.execute(
            select(Contact).where(Contact.company_id == secondary_id)
        )
        for contact in contacts_result.scalars().all():
            contact.company_id = primary_id

        # Transfer activities, notes, tags
        await self._transfer_entity_links("companies", secondary_id, primary_id)

        # Delete secondary
        await self.db.delete(secondary)
        await self.db.flush()
        await self.db.refresh(primary)
        return primary

    async def merge_leads(
        self,
        primary_id: int,
        secondary_id: int,
    ) -> Lead:
        """Merge secondary lead into primary. Transfers activities, notes, and tags."""
        primary = await self.db.execute(
            select(Lead).where(Lead.id == primary_id)
        )
        primary = primary.scalar_one_or_none()
        if not primary:
            raise ValueError(f"Primary lead {primary_id} not found")

        secondary = await self.db.execute(
            select(Lead).where(Lead.id == secondary_id)
        )
        secondary = secondary.scalar_one_or_none()
        if not secondary:
            raise ValueError(f"Secondary lead {secondary_id} not found")

        # Transfer activities, notes, tags
        await self._transfer_entity_links("leads", secondary_id, primary_id)

        # Delete secondary
        await self.db.delete(secondary)
        await self.db.flush()
        await self.db.refresh(primary)
        return primary

    async def _transfer_entity_links(
        self,
        entity_type: str,
        from_id: int,
        to_id: int,
    ) -> None:
        """Transfer activities, notes, and tags from one entity to another."""
        # Transfer activities
        activities_result = await self.db.execute(
            select(Activity)
            .where(Activity.entity_type == entity_type)
            .where(Activity.entity_id == from_id)
        )
        for activity in activities_result.scalars().all():
            activity.entity_id = to_id

        # Transfer notes
        notes_result = await self.db.execute(
            select(Note)
            .where(Note.entity_type == entity_type)
            .where(Note.entity_id == from_id)
        )
        for note in notes_result.scalars().all():
            note.entity_id = to_id

        # Transfer tags (avoid duplicates)
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
