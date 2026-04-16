"""CSV import/export handler with smart column mapping and duplicate detection."""

import csv
import io
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any, Dict, List, Set, Type

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.companies.models import Company
from src.contacts.models import Contact
from src.leads.models import Lead
from src.import_export.csv_column_mapper import (
    map_columns,
    find_name_column,
    find_location_column,
    find_contact_person_column,
    detect_linkedin_format,
    detect_monday_csv,
    apply_monday_status,
    split_full_name,
    split_location,
    normalize_header,
)

# Re-export module-level helpers so callers that imported them from here still work
__all__ = [
    "CSVHandler",
    "map_columns",
    "find_name_column",
    "find_location_column",
    "find_contact_person_column",
    "detect_linkedin_format",
    "detect_monday_csv",
    "apply_monday_status",
    "split_full_name",
    "split_location",
    "normalize_header",
]


class CSVHandler:
    """Handles CSV import and export for CRM entities."""

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
        "description", "status", "link_creative_tier", "sow_url", "account_manager",
    ]

    LEAD_FIELDS = [
        "first_name", "last_name", "email", "phone", "mobile",
        "job_title", "company_name", "website", "industry",
        "source_id", "source_details", "status",
        "address_line1", "address_line2", "city", "state", "postal_code", "country",
        "description", "requirements", "budget_amount", "budget_currency",
    ]

    NUMERIC_INT_FIELDS = {"company_id", "source_id", "annual_revenue", "employee_count"}
    NUMERIC_FLOAT_FIELDS = {"budget_amount"}

    def __init__(self, db: AsyncSession):
        self.db = db

    def _get_fields(self, entity_type: str) -> List[str]:
        return {"contacts": self.CONTACT_FIELDS, "companies": self.COMPANY_FIELDS, "leads": self.LEAD_FIELDS}[entity_type]

    def _get_model(self, entity_type: str) -> Type:
        return {"contacts": Contact, "companies": Company, "leads": Lead}[entity_type]

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    async def export_contacts(self, user_id: int = None) -> str:
        query = select(Contact)
        if user_id:
            query = query.where(Contact.owner_id == user_id)
        result = await self.db.execute(query)
        return self._to_csv(result.scalars().all(), self.CONTACT_FIELDS)

    async def export_companies(self, user_id: int = None) -> str:
        query = select(Company)
        if user_id:
            query = query.where(Company.owner_id == user_id)
        result = await self.db.execute(query)
        return self._to_csv(result.scalars().all(), self.COMPANY_FIELDS)

    async def export_leads(self, user_id: int = None) -> str:
        query = select(Lead)
        if user_id:
            query = query.where(Lead.owner_id == user_id)
        result = await self.db.execute(query)
        return self._to_csv(result.scalars().all(), self.LEAD_FIELDS)

    # ------------------------------------------------------------------
    # Import
    # ------------------------------------------------------------------

    async def import_contacts(self, csv_content: str, user_id: int, skip_errors: bool = True) -> Dict[str, Any]:
        return await self._import_entities(csv_content, Contact, self.CONTACT_FIELDS, user_id, skip_errors)

    async def import_companies(
        self,
        csv_content: str,
        user_id: int,
        skip_errors: bool = True,
        contact_decisions: List[Dict[str, Any]] | None = None,
    ) -> Dict[str, Any]:
        """Import companies with optional auto-creation of linked contacts."""
        reader = csv.DictReader(io.StringIO(csv_content))
        csv_headers = reader.fieldnames or []

        column_mapping = map_columns(csv_headers, self.COMPANY_FIELDS)
        name_col = find_name_column(csv_headers, column_mapping, self.COMPANY_FIELDS)
        location_col = find_location_column(csv_headers, column_mapping, self.COMPANY_FIELDS)
        contact_person_col = find_contact_person_column(csv_headers, column_mapping)

        decision_map: Dict[str, Dict[str, Any]] = {}
        if contact_decisions:
            for d in contact_decisions:
                decision_map[d["csv_name"].strip().lower()] = d

        existing_emails = await self._get_existing_emails(Company)
        existing_names = await self._get_existing_names(Company)
        seen_emails: Set[str] = set()
        seen_names: Set[str] = set()

        imported = 0
        contacts_created = 0
        contacts_linked = 0
        errors = []
        duplicates_skipped = 0
        duplicates = []
        row_num = 1

        for row in reader:
            row_num += 1
            try:
                entity_data = {}
                for csv_col, target_field in column_mapping.items():
                    raw = row.get(csv_col, "")
                    if raw:
                        entity_data[target_field] = self._parse_value(target_field, raw)

                if name_col:
                    raw_name = row.get(name_col, "").strip()
                    if raw_name:
                        first, last = split_full_name(raw_name)
                        entity_data["first_name"] = first
                        entity_data["last_name"] = last

                if location_col:
                    raw_loc = row.get(location_col, "").strip()
                    if raw_loc:
                        city, state = split_location(raw_loc)
                        entity_data["city"] = city
                        entity_data["state"] = state

                email = (entity_data.get("email") or "").lower()
                if email:
                    if email in existing_emails or email in seen_emails:
                        duplicates_skipped += 1
                        label = entity_data.get("name") or ""
                        duplicates.append({"row": row_num, "email": email, "label": label})
                        continue
                    seen_emails.add(email)

                company_name = (entity_data.get("name") or "").strip().lower()
                if company_name and not email:
                    if company_name in existing_names or company_name in seen_names:
                        duplicates_skipped += 1
                        duplicates.append({"row": row_num, "email": "", "label": entity_data.get("name") or ""})
                        continue
                    seen_names.add(company_name)

                company = Company(**entity_data, owner_id=user_id, created_by_id=user_id)
                self.db.add(company)

                if skip_errors:
                    try:
                        await self.db.flush()
                        imported += 1
                    except Exception as flush_exc:
                        await self.db.rollback()
                        errors.append(f"Row {row_num}: {flush_exc!s}")
                        continue
                else:
                    await self.db.flush()
                    imported += 1

                if contact_person_col:
                    raw_contact = row.get(contact_person_col, "").strip()
                    if raw_contact:
                        contact_names = [n.strip() for n in raw_contact.split(",") if n.strip()]
                        for contact_name in contact_names:
                            name_key = contact_name.strip().lower()
                            decision = decision_map.get(name_key, {"action": "create_new"})
                            action = decision.get("action", "create_new")

                            if action == "skip":
                                continue
                            elif action == "link_existing" and decision.get("contact_id"):
                                from sqlalchemy import update
                                await self.db.execute(
                                    update(Contact)
                                    .where(Contact.id == decision["contact_id"])
                                    .values(company_id=company.id)
                                )
                                contacts_linked += 1
                            else:
                                first, last = split_full_name(contact_name)
                                contact = Contact(
                                    first_name=first,
                                    last_name=last or first,
                                    company_id=company.id,
                                    owner_id=user_id,
                                    created_by_id=user_id,
                                )
                                self.db.add(contact)
                                try:
                                    await self.db.flush()
                                    contacts_created += 1
                                except Exception as contact_exc:
                                    await self.db.rollback()
                                    errors.append(f"Row {row_num}: contact '{contact_name}': {contact_exc!s}")

            except Exception as e:
                errors.append(f"Row {row_num}: {e!s}")
                if not skip_errors:
                    await self.db.rollback()
                    return {"imported": 0, "errors": errors, "success": False, "duplicates_skipped": duplicates_skipped}

        return {
            "imported": imported,
            "contacts_created": contacts_created,
            "contacts_linked": contacts_linked,
            "errors": errors,
            "success": True,
            "duplicates_skipped": duplicates_skipped,
            "duplicates": duplicates,
        }

    async def import_leads(self, csv_content: str, user_id: int, skip_errors: bool = True) -> Dict[str, Any]:
        return await self._import_entities(csv_content, Lead, self.LEAD_FIELDS, user_id, skip_errors)

    # ------------------------------------------------------------------
    # Preview (no DB writes)
    # ------------------------------------------------------------------

    async def import_with_mapping(
        self,
        entity_type: str,
        csv_content: str,
        column_mapping: Dict[str, str],
        user_id: int,
        skip_errors: bool = True,
    ) -> Dict[str, Any]:
        """Import entities using user-specified column mapping."""
        entity_class = self._get_model(entity_type)
        fields = self._get_fields(entity_type)

        for csv_col, target_field in column_mapping.items():
            if target_field not in fields and target_field not in ("skip", ""):
                raise ValueError(f"Invalid target field '{target_field}' for {entity_type}")

        active_mapping = {k: v for k, v in column_mapping.items() if v and v != "skip"}

        return await self._import_entities(csv_content, entity_class, fields, user_id, skip_errors, active_mapping)

    async def preview_csv(self, entity_type: str, csv_content: str) -> Dict[str, Any]:
        """Preview a CSV: show column mapping, first rows, and validation warnings."""
        fields = self._get_fields(entity_type)
        reader = csv.DictReader(io.StringIO(csv_content))
        csv_headers = reader.fieldnames or []

        column_mapping = map_columns(csv_headers, fields)
        name_col = find_name_column(csv_headers, column_mapping, fields)
        location_col = find_location_column(csv_headers, column_mapping, fields)
        contact_person_col = find_contact_person_column(csv_headers, column_mapping) if entity_type == "companies" else None
        special_cols = {name_col, location_col, contact_person_col} - {None}
        unmapped = [h for h in csv_headers if h not in column_mapping and h not in special_cols]
        missing_fields = [f for f in fields if f not in column_mapping.values()]
        if name_col:
            missing_fields = [f for f in missing_fields if f not in ("first_name", "last_name")]
        if location_col:
            missing_fields = [f for f in missing_fields if f not in ("city", "state")]

        existing_contacts = []
        if contact_person_col:
            result = await self.db.execute(
                select(Contact.id, Contact.first_name, Contact.last_name, Contact.email, Contact.company_id)
            )
            existing_contacts = result.all()

        all_rows_raw = list(csv.DictReader(io.StringIO(csv_content)))
        total_rows = len(all_rows_raw)

        preview_rows = []
        warnings = []
        emails_seen: Set[str] = set()
        contact_matches: List[Dict[str, Any]] = []

        for i, row in enumerate(all_rows_raw):
            mapped_row = {}
            for csv_col, target_field in column_mapping.items():
                mapped_row[target_field] = row.get(csv_col, "").strip()
            if name_col:
                raw_name = row.get(name_col, "").strip()
                if raw_name:
                    first, last = split_full_name(raw_name)
                    mapped_row["first_name"] = first
                    mapped_row["last_name"] = last
            if location_col:
                raw_loc = row.get(location_col, "").strip()
                if raw_loc:
                    city, state = split_location(raw_loc)
                    mapped_row["city"] = city
                    mapped_row["state"] = state

            if i < 5:
                preview_rows.append(mapped_row)

            email = mapped_row.get("email", "").lower()
            if email:
                if email in emails_seen:
                    warnings.append(f"Row {i + 2}: duplicate email '{email}' within file")
                emails_seen.add(email)

            if contact_person_col:
                raw_contact = row.get(contact_person_col, "").strip()
                if raw_contact:
                    contact_names = [n.strip() for n in raw_contact.split(",") if n.strip()]
                    for contact_name in contact_names:
                        first, last = split_full_name(contact_name)
                        full_name_csv = f"{first} {last}".strip().lower()
                        candidates = []
                        for c in existing_contacts:
                            full_name_db = f"{c.first_name} {c.last_name}".strip().lower()
                            score = SequenceMatcher(None, full_name_csv, full_name_db).ratio()
                            if score >= 0.5:
                                candidates.append({
                                    "contact_id": c.id,
                                    "name": f"{c.first_name} {c.last_name}",
                                    "email": c.email,
                                    "match_pct": round(score * 100),
                                })
                        candidates.sort(key=lambda x: x["match_pct"], reverse=True)
                        contact_matches.append({
                            "row": i + 2,
                            "csv_name": contact_name,
                            "first_name": first,
                            "last_name": last,
                            "candidates": candidates[:5],
                        })

        is_linkedin = detect_linkedin_format(csv_headers)
        if is_linkedin:
            source_detected = "linkedin_sales_navigator"
        elif detect_monday_csv(csv_headers):
            source_detected = "monday.com"
        else:
            source_detected = None

        result = {
            "total_rows": total_rows,
            "csv_headers": csv_headers,
            "available_fields": fields,
            "column_mapping": column_mapping,
            "unmapped_columns": unmapped,
            "missing_fields": missing_fields,
            "preview_rows": preview_rows,
            "warnings": warnings,
            "source_detected": source_detected,
        }
        if contact_person_col:
            result["contact_person_column"] = contact_person_col
            result["contact_matches"] = contact_matches
        return result

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _sanitize_csv_value(value: str) -> str:
        if value and isinstance(value, str) and value[0] in ("=", "+", "-", "@"):
            return "'" + value
        return value

    def _to_csv(self, entities: List[Any], fields: List[str]) -> str:
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
                cell = value or ""
                if isinstance(cell, str):
                    cell = self._sanitize_csv_value(cell)
                row[field] = cell
            writer.writerow(row)
        return output.getvalue()

    async def _get_existing_names(self, entity_class: Type) -> Set[str]:
        if not hasattr(entity_class, "name"):
            return set()
        result = await self.db.execute(
            select(func.lower(entity_class.name)).where(entity_class.name.isnot(None))
        )
        return {row[0] for row in result.all()}

    async def _get_existing_emails(self, entity_class: Type) -> Set[str]:
        if not hasattr(entity_class, "email"):
            return set()
        result = await self.db.execute(
            select(func.lower(entity_class.email)).where(entity_class.email.isnot(None))
        )
        return {row[0] for row in result.all()}

    def _parse_value(self, field: str, raw: str) -> Any:
        value = raw.strip()
        if not value:
            return None
        if field in self.NUMERIC_INT_FIELDS:
            return int(value)
        if field in self.NUMERIC_FLOAT_FIELDS:
            return float(value)
        return value

    async def _import_entities(
        self,
        csv_content: str,
        entity_class: Type,
        fields: List[str],
        user_id: int,
        skip_errors: bool = True,
        column_mapping: Dict[str, str] | None = None,
    ) -> Dict[str, Any]:
        reader = csv.DictReader(io.StringIO(csv_content))
        csv_headers = reader.fieldnames or []

        if column_mapping is None:
            column_mapping = map_columns(csv_headers, fields)
        name_col = find_name_column(csv_headers, column_mapping, fields)
        location_col = find_location_column(csv_headers, column_mapping, fields)
        is_monday = detect_monday_csv(csv_headers)
        is_linkedin = detect_linkedin_format(csv_headers)

        existing_emails = await self._get_existing_emails(entity_class)
        seen_emails: Set[str] = set()

        imported = 0
        errors = []
        duplicates_skipped = 0
        duplicates = []
        row_num = 1

        for row in reader:
            row_num += 1
            try:
                entity_data = {}
                for csv_col, target_field in column_mapping.items():
                    raw = row.get(csv_col, "")
                    if raw:
                        entity_data[target_field] = self._parse_value(target_field, raw)

                if name_col:
                    raw_name = row.get(name_col, "").strip()
                    if raw_name:
                        first, last = split_full_name(raw_name)
                        entity_data["first_name"] = first
                        entity_data["last_name"] = last

                if location_col:
                    raw_loc = row.get(location_col, "").strip()
                    if raw_loc:
                        city, state = split_location(raw_loc)
                        entity_data["city"] = city
                        entity_data["state"] = state

                if is_monday and "status" in entity_data and entity_data["status"]:
                    entity_data["status"] = apply_monday_status(entity_data["status"])

                if is_linkedin and hasattr(entity_class, "source_details"):
                    entity_data.setdefault("source_details", "linkedin_sales_navigator")

                email = (entity_data.get("email") or "").lower()
                if email:
                    if email in existing_emails or email in seen_emails:
                        duplicates_skipped += 1
                        first = entity_data.get("first_name") or ""
                        last = entity_data.get("last_name") or ""
                        label = f"{first} {last}".strip()
                        label = label or entity_data.get("company_name") or entity_data.get("name") or ""
                        duplicates.append({"row": row_num, "email": email, "label": label})
                        continue
                    seen_emails.add(email)

                entity = entity_class(**entity_data, owner_id=user_id, created_by_id=user_id)

                if skip_errors:
                    async with self.db.begin_nested():
                        self.db.add(entity)
                        try:
                            await self.db.flush()
                            imported += 1
                        except Exception as flush_exc:
                            errors.append(f"Row {row_num}: {flush_exc!s}")
                else:
                    self.db.add(entity)
                    imported += 1

            except Exception as e:
                errors.append(f"Row {row_num}: {e!s}")
                if not skip_errors:
                    return {"imported": 0, "errors": errors, "success": False, "duplicates_skipped": duplicates_skipped}

        if not skip_errors:
            await self.db.flush()

        return {
            "imported": imported,
            "errors": errors,
            "success": True,
            "duplicates_skipped": duplicates_skipped,
            "duplicates": duplicates,
        }

    def get_template(self, entity_type: str) -> str:
        fields = self._get_fields(entity_type)
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        return output.getvalue()
