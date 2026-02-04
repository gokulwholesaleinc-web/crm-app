"""
Lead conversion following ERPNext pattern.

Conversion flows:
1. Lead → Contact (creates a contact record from lead data)
2. Lead → Opportunity (creates an opportunity with lead as source)
3. Lead → Contact + Opportunity (both at once)
"""

from typing import Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from src.leads.models import Lead, LeadStatus
from src.contacts.models import Contact
from src.companies.models import Company


class LeadConverter:
    """Handles lead conversion operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def convert_to_contact(
        self,
        lead: Lead,
        user_id: int,
        company_id: Optional[int] = None,
        create_company: bool = False,
    ) -> Tuple[Contact, Optional[Company]]:
        """
        Convert a lead to a contact.

        Args:
            lead: The lead to convert
            user_id: The user performing the conversion
            company_id: Optional existing company to link to
            create_company: If True and lead has company_name, create a company

        Returns:
            Tuple of (created_contact, created_company_or_none)
        """
        created_company = None

        # Create company if requested
        if create_company and lead.company_name and not company_id:
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

        # Create contact from lead data
        contact = Contact(
            first_name=lead.first_name,
            last_name=lead.last_name,
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
            owner_id=lead.owner_id or user_id,
            created_by_id=user_id,
        )
        self.db.add(contact)
        await self.db.flush()

        # Update lead with conversion info
        lead.converted_contact_id = contact.id
        lead.status = LeadStatus.CONVERTED.value
        await self.db.flush()

        await self.db.refresh(contact)
        if created_company:
            await self.db.refresh(created_company)

        return contact, created_company

    async def convert_to_opportunity(
        self,
        lead: Lead,
        user_id: int,
        pipeline_stage_id: int,
        contact_id: Optional[int] = None,
        company_id: Optional[int] = None,
    ):
        """
        Convert a lead to an opportunity.

        Note: This method imports Opportunity locally to avoid circular imports.

        Args:
            lead: The lead to convert
            user_id: The user performing the conversion
            pipeline_stage_id: Initial pipeline stage for the opportunity
            contact_id: Optional contact to link (if lead was converted to contact first)
            company_id: Optional company to link

        Returns:
            Created opportunity
        """
        # Local import to avoid circular dependency
        from src.opportunities.models import Opportunity

        opportunity = Opportunity(
            name=f"{lead.full_name} - Opportunity",
            contact_id=contact_id,
            company_id=company_id,
            pipeline_stage_id=pipeline_stage_id,
            amount=lead.budget_amount,
            currency=lead.budget_currency,
            source=f"Lead #{lead.id}",
            description=lead.description or lead.requirements,
            owner_id=lead.owner_id or user_id,
            created_by_id=user_id,
        )
        self.db.add(opportunity)
        await self.db.flush()

        # Update lead with conversion info
        lead.converted_opportunity_id = opportunity.id
        if lead.status != LeadStatus.CONVERTED.value:
            lead.status = LeadStatus.CONVERTED.value
        await self.db.flush()

        await self.db.refresh(opportunity)
        return opportunity

    async def full_conversion(
        self,
        lead: Lead,
        user_id: int,
        pipeline_stage_id: int,
        create_company: bool = True,
    ):
        """
        Full conversion: Lead → Company + Contact + Opportunity.

        Returns:
            Tuple of (contact, company_or_none, opportunity)
        """
        # First convert to contact (optionally with company)
        contact, company = await self.convert_to_contact(
            lead=lead,
            user_id=user_id,
            create_company=create_company,
        )

        # Then convert to opportunity
        opportunity = await self.convert_to_opportunity(
            lead=lead,
            user_id=user_id,
            pipeline_stage_id=pipeline_stage_id,
            contact_id=contact.id,
            company_id=company.id if company else None,
        )

        return contact, company, opportunity
