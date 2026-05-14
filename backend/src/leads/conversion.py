"""Lead conversion: Lead → Contact (+ Company).

The Opportunity step Lorenzo flagged as redundant on 2026-05-14 is gone —
Won-stage leads now produce a Contact (and optionally a Company) only;
proposals are created manually off the resulting Contact. Historical
``converted_opportunity_id`` rows are preserved but no new values are
written from this path.
"""

import logging

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.activities.models import Activity
from src.companies.models import Company
from src.contacts.models import Contact
from src.core.models import EntityTag, Note
from src.leads.models import Lead, LeadStatus

logger = logging.getLogger(__name__)


class LeadConverter:
    """Handles lead conversion operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def convert_to_contact(
        self,
        lead: Lead,
        user_id: int,
        company_id: int | None = None,
        create_company: bool = False,
    ) -> tuple[Contact, Company | None]:
        """
        Convert a lead to a contact.

        If a contact with the lead's email (or any of its aliases) already
        exists, link the lead to that contact instead of inserting a
        duplicate — the unique index on contacts.email would otherwise
        500 the request, which broke the auto-convert path on the kanban
        Won-stage drop for any lead whose email had been added as a
        contact through some other path (manual create, Gmail sync,
        etc.). Cascades still run against the existing contact so
        lead-attached tags/activities/notes don't orphan.

        Args:
            lead: The lead to convert
            user_id: The user performing the conversion
            company_id: Optional existing company to link to
            create_company: If True and lead has company_name, create a company

        Returns:
            Tuple of (resulting_contact, created_company_or_none) — the
            contact may be pre-existing.
        """
        from src.contacts.alias_match import find_contact_id_by_any_email

        created_company = None

        # Look up the contact match BEFORE deciding whether to spawn a
        # Company. Reusing an existing contact means the lead's
        # company_name is redundant — the existing contact already has
        # whatever company they belong to. Creating one anyway would
        # leave an orphan Company row that nothing references.
        existing_contact: Contact | None = None
        if lead.email:
            _etype, existing_id = await find_contact_id_by_any_email([lead.email], self.db)
            if existing_id is not None:
                existing_contact = await self.db.get(Contact, existing_id)

        # Create company if requested AND we're going to create a fresh
        # contact. Skipped on reuse — see comment above.
        if (
            existing_contact is None
            and create_company
            and lead.company_name
            and not company_id
        ):
            created_company = Company(
                name=lead.company_name,
                website=lead.website,
                industry=lead.industry,
                phone=lead.phone,
                status="prospect",
                created_by_id=user_id,
            )
            self.db.add(created_company)
            await self.db.flush()
            company_id = created_company.id

        if existing_contact is not None:
            contact = existing_contact
        else:
            # Create contact from lead data — contacts require first_name, so
            # fall back to company_name for company-only leads.
            contact = Contact(
                first_name=lead.first_name or lead.company_name or "Unknown",
                last_name=lead.last_name or "",
                email=lead.email,
                phone=lead.phone,
                mobile=lead.mobile,
                job_title=lead.job_title,
                company_id=company_id,
                address_line1=lead.address_line1,
                address_line2=lead.address_line2,
                city=lead.city,
                state=lead.state,
                postal_code=lead.postal_code,
                country=lead.country,
                description=lead.description,
                sales_code=lead.sales_code,
                owner_id=lead.owner_id or user_id,
                created_by_id=user_id,
            )
            self.db.add(contact)
            await self.db.flush()

        # Cascade lead-attached records onto the (new OR pre-existing)
        # contact so nothing is silently orphaned post-conversion. The
        # cascade helpers all skip duplicates / no-op on empty input,
        # so re-running against an existing contact is safe.
        await self._relink_tags(lead.id, contact.id)
        await self._relink_activities(lead.id, contact.id)
        await self._relink_notes(lead.id, contact.id)

        # Update lead with conversion info
        lead.converted_contact_id = contact.id
        lead.status = LeadStatus.CONVERTED.value
        await self.db.flush()

        await self.db.refresh(contact)
        if created_company:
            await self.db.refresh(created_company)

        return contact, created_company

    async def _relink_tags(self, lead_id: int, contact_id: int) -> int:
        """Copy entity_tags rows from lead → contact, skipping duplicates.

        Single-tenant only: lead_id / contact_id are caller-supplied so a
        cross-tenant call would silently rewire a lead's tags onto a
        contact in a different tenant. Mirrors the comments in
        ``payments/webhook_processor.py`` where a similar tenant_id
        filter is the explicit follow-up if a second tenant onboards.
        """
        existing = await self.db.execute(
            select(EntityTag.tag_id).where(
                EntityTag.entity_type == "contacts",
                EntityTag.entity_id == contact_id,
            )
        )
        existing_tag_ids = {row[0] for row in existing.all()}

        result = await self.db.execute(
            select(EntityTag.tag_id).where(
                EntityTag.entity_type == "leads",
                EntityTag.entity_id == lead_id,
            )
        )
        lead_tag_ids = {row[0] for row in result.all()}

        new_tag_ids = lead_tag_ids - existing_tag_ids
        for tag_id in new_tag_ids:
            self.db.add(
                EntityTag(
                    tag_id=tag_id,
                    entity_type="contacts",
                    entity_id=contact_id,
                )
            )
        if new_tag_ids:
            await self.db.flush()
        logger.debug(
            "re-linked %d tags from lead %d → contact %d",
            len(new_tag_ids), lead_id, contact_id,
        )
        return len(new_tag_ids)

    async def _relink_activities(self, lead_id: int, contact_id: int) -> int:
        """Move activities from lead → contact (UPDATE, not duplicate)."""
        result = await self.db.execute(
            update(Activity)
            .where(
                Activity.entity_type == "leads",
                Activity.entity_id == lead_id,
            )
            .values(entity_type="contacts", entity_id=contact_id)
        )
        count = result.rowcount or 0
        logger.debug(
            "re-linked %d activities from lead %d → contact %d",
            count, lead_id, contact_id,
        )
        return count

    async def _relink_notes(self, lead_id: int, contact_id: int) -> int:
        """Move notes from lead → contact (UPDATE, not duplicate)."""
        result = await self.db.execute(
            update(Note)
            .where(
                Note.entity_type == "leads",
                Note.entity_id == lead_id,
            )
            .values(entity_type="contacts", entity_id=contact_id)
        )
        count = result.rowcount or 0
        logger.debug(
            "re-linked %d notes from lead %d → contact %d",
            count, lead_id, contact_id,
        )
        return count

    async def full_conversion(
        self,
        lead: Lead,
        user_id: int,
        create_company: bool = True,
    ) -> tuple[Contact, Company | None]:
        """Won-stage conversion: Lead → Contact (+ Company).

        Wraps ``convert_to_contact`` so the lead router's stage-change
        helper has a stable name to call. The Opportunity creation step
        was removed when Lorenzo collapsed the pipeline to leads-only on
        2026-05-14.
        """
        return await self.convert_to_contact(
            lead=lead,
            user_id=user_id,
            create_company=create_company,
        )
