"""CSV import/export handler."""

import csv
import io
from typing import List, Dict, Any, Type, Optional
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.contacts.models import Contact
from src.companies.models import Company
from src.leads.models import Lead


class CSVHandler:
    """Handles CSV import and export for CRM entities."""

    # Field mappings for each entity type
    CONTACT_FIELDS = [
        "first_name", "last_name", "email", "phone", "mobile",
        "job_title", "department", "company_id",
        "address_line1", "address_line2", "city", "state", "postal_code", "country",
        "linkedin_url", "twitter_handle", "description", "status",
    ]

    COMPANY_FIELDS = [
        "name", "website", "industry", "company_size", "phone", "email",
        "address_line1", "address_line2", "city", "state", "postal_code", "country",
        "annual_revenue", "employee_count", "linkedin_url", "twitter_handle",
        "description", "status",
    ]

    LEAD_FIELDS = [
        "first_name", "last_name", "email", "phone", "mobile",
        "job_title", "company_name", "website", "industry",
        "source_id", "source_details", "status",
        "address_line1", "address_line2", "city", "state", "postal_code", "country",
        "description", "requirements", "budget_amount", "budget_currency",
    ]

    def __init__(self, db: AsyncSession):
        self.db = db

    async def export_contacts(self, user_id: int = None) -> str:
        """Export contacts to CSV, scoped to user."""
        query = select(Contact)
        if user_id:
            query = query.where(Contact.owner_id == user_id)
        result = await self.db.execute(query)
        contacts = result.scalars().all()

        return self._to_csv(contacts, self.CONTACT_FIELDS)

    async def export_companies(self, user_id: int = None) -> str:
        """Export companies to CSV, scoped to user."""
        query = select(Company)
        if user_id:
            query = query.where(Company.owner_id == user_id)
        result = await self.db.execute(query)
        companies = result.scalars().all()

        return self._to_csv(companies, self.COMPANY_FIELDS)

    async def export_leads(self, user_id: int = None) -> str:
        """Export leads to CSV, scoped to user."""
        query = select(Lead)
        if user_id:
            query = query.where(Lead.owner_id == user_id)
        result = await self.db.execute(query)
        leads = result.scalars().all()

        return self._to_csv(leads, self.LEAD_FIELDS)

    async def import_contacts(
        self,
        csv_content: str,
        user_id: int,
        skip_errors: bool = True,
    ) -> Dict[str, Any]:
        """Import contacts from CSV."""
        return await self._import_entities(
            csv_content=csv_content,
            entity_class=Contact,
            fields=self.CONTACT_FIELDS,
            user_id=user_id,
            skip_errors=skip_errors,
        )

    async def import_companies(
        self,
        csv_content: str,
        user_id: int,
        skip_errors: bool = True,
    ) -> Dict[str, Any]:
        """Import companies from CSV."""
        return await self._import_entities(
            csv_content=csv_content,
            entity_class=Company,
            fields=self.COMPANY_FIELDS,
            user_id=user_id,
            skip_errors=skip_errors,
        )

    async def import_leads(
        self,
        csv_content: str,
        user_id: int,
        skip_errors: bool = True,
    ) -> Dict[str, Any]:
        """Import leads from CSV."""
        return await self._import_entities(
            csv_content=csv_content,
            entity_class=Lead,
            fields=self.LEAD_FIELDS,
            user_id=user_id,
            skip_errors=skip_errors,
        )

    def _to_csv(self, entities: List[Any], fields: List[str]) -> str:
        """Convert entities to CSV string."""
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()

        for entity in entities:
            row = {}
            for field in fields:
                value = getattr(entity, field, None)
                if value is not None:
                    if isinstance(value, datetime):
                        value = value.isoformat()
                row[field] = value or ""
            writer.writerow(row)

        return output.getvalue()

    async def _import_entities(
        self,
        csv_content: str,
        entity_class: Type,
        fields: List[str],
        user_id: int,
        skip_errors: bool = True,
    ) -> Dict[str, Any]:
        """Generic entity import from CSV."""
        reader = csv.DictReader(io.StringIO(csv_content))

        imported = 0
        errors = []
        row_num = 1  # Header is row 0

        for row in reader:
            row_num += 1
            try:
                # Filter to only valid fields
                entity_data = {}
                for field in fields:
                    if field in row and row[field]:
                        value = row[field].strip()
                        # Handle numeric fields
                        if field in ["company_id", "source_id", "annual_revenue", "employee_count"]:
                            if value:
                                value = int(value)
                            else:
                                value = None
                        elif field in ["budget_amount"]:
                            if value:
                                value = float(value)
                            else:
                                value = None
                        entity_data[field] = value

                # Create entity with owner_id for data scoping
                entity = entity_class(**entity_data, owner_id=user_id, created_by_id=user_id)
                self.db.add(entity)

                if skip_errors:
                    try:
                        await self.db.flush()
                        imported += 1
                    except Exception as flush_exc:
                        await self.db.rollback()
                        error_msg = f"Row {row_num}: {str(flush_exc)}"
                        errors.append(error_msg)
                else:
                    imported += 1

            except Exception as e:
                error_msg = f"Row {row_num}: {str(e)}"
                errors.append(error_msg)
                if not skip_errors:
                    await self.db.rollback()
                    return {
                        "imported": 0,
                        "errors": errors,
                        "success": False,
                    }

        if not skip_errors:
            await self.db.flush()

        return {
            "imported": imported,
            "errors": errors,
            "success": True,
        }

    def get_template(self, entity_type: str) -> str:
        """Get CSV template for an entity type."""
        if entity_type == "contacts":
            fields = self.CONTACT_FIELDS
        elif entity_type == "companies":
            fields = self.COMPANY_FIELDS
        elif entity_type == "leads":
            fields = self.LEAD_FIELDS
        else:
            raise ValueError(f"Unknown entity type: {entity_type}")

        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        return output.getvalue()
