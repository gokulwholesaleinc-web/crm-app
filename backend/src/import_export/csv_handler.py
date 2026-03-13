"""CSV import/export handler with smart column mapping and duplicate detection."""

import csv
import io
import re
from typing import List, Dict, Any, Type, Optional, Set
from datetime import datetime
from difflib import SequenceMatcher
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from src.contacts.models import Contact
from src.companies.models import Company
from src.leads.models import Lead


# Common aliases for CSV columns → internal field names
COLUMN_ALIASES: Dict[str, str] = {
    "firstname": "first_name",
    "first": "first_name",
    "fname": "first_name",
    "lastname": "last_name",
    "last": "last_name",
    "lname": "last_name",
    "surname": "last_name",
    "emailaddress": "email",
    "email_address": "email",
    "e_mail": "email",
    "phonenumber": "phone",
    "phone_number": "phone",
    "telephone": "phone",
    "tel": "phone",
    "mobilephone": "mobile",
    "mobile_phone": "mobile",
    "cell": "mobile",
    "cellphone": "mobile",
    "cell_phone": "mobile",
    "jobtitle": "job_title",
    "job": "job_title",
    "title": "job_title",
    "position": "job_title",
    "dept": "department",
    "company": "company_name",
    "companyname": "company_name",
    "company_id": "company_id",
    "companyid": "company_id",
    "address": "address_line1",
    "address1": "address_line1",
    "street": "address_line1",
    "address2": "address_line2",
    "zip": "postal_code",
    "zipcode": "postal_code",
    "zip_code": "postal_code",
    "postcode": "postal_code",
    "linkedin": "linkedin_url",
    "linkedinurl": "linkedin_url",
    "twitter": "twitter_handle",
    "twitterhandle": "twitter_handle",
    "desc": "description",
    "notes": "description",
    "site": "website",
    "url": "website",
    "web": "website",
    "companysize": "company_size",
    "size": "company_size",
    "revenue": "annual_revenue",
    "annualrevenue": "annual_revenue",
    "employees": "employee_count",
    "employeecount": "employee_count",
    "num_employees": "employee_count",
    "source": "source_id",
    "sourceid": "source_id",
    "sourcedetails": "source_details",
    "source_detail": "source_details",
    "budget": "budget_amount",
    "budgetamount": "budget_amount",
    "currency": "budget_currency",
    "budgetcurrency": "budget_currency",
    "reqs": "requirements",
    "requirement": "requirements",
    # Monday.com specific aliases
    "leadstatus": "status",
    "lead_status": "status",
    "location": "address_line1",
    "link": "website",
    "text": "description",
    # Domain / URL aliases
    "domain": "website",
    "domainname": "website",
    "websiteurl": "website",
    "homepage": "website",
    # Business size aliases
    "businesssizetier": "company_size",
    "businesssize": "company_size",
    "tier": "company_size",
    "companytier": "company_size",
    "sizetier": "company_size",
}

# Headers that represent a full name (to be split into first_name + last_name)
FULL_NAME_HEADERS = {"name", "fullname", "person", "contactname", "leadname"}

# Headers that represent a combined location (to be split into city + state)
LOCATION_HEADERS = {"hqlocation", "hqaddress", "headquarterslocation", "headquarters", "cityst", "citystate"}

# Headers that represent a contact person name (for auto-creating linked contacts on company import)
CONTACT_PERSON_HEADERS = {"pointofcontact", "poc", "contactperson", "primarycontact", "contactname", "contact"}

FUZZY_MATCH_THRESHOLD = 0.75


def _split_full_name(full_name: str) -> tuple:
    """Split 'John Smith' into ('John', 'Smith')."""
    parts = full_name.strip().split(None, 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return (parts[0], "") if parts else ("", "")


def _split_location(location: str) -> tuple:
    """Split 'Springfield, IL' into ('Springfield', 'IL')."""
    parts = [p.strip() for p in location.strip().split(",", 1)]
    if len(parts) == 2:
        return parts[0], parts[1]
    return (parts[0], "") if parts else ("", "")


def _find_name_column(csv_headers: list, column_mapping: dict, target_fields: list):
    """Find a full-name CSV column that should be split into first_name + last_name.

    Returns the CSV header name if found, None otherwise.
    """
    if "first_name" not in target_fields or "last_name" not in target_fields:
        return None
    mapped_fields = set(column_mapping.values())
    if "first_name" in mapped_fields or "last_name" in mapped_fields:
        return None
    for header in csv_headers:
        normalized = _normalize_header(header)
        if normalized in FULL_NAME_HEADERS:
            return header
    return None


def _find_location_column(csv_headers: list, column_mapping: dict, target_fields: list):
    """Find a combined location CSV column that should be split into city + state.

    Returns the CSV header name if found, None otherwise.
    """
    if "city" not in target_fields or "state" not in target_fields:
        return None
    mapped_fields = set(column_mapping.values())
    if "city" in mapped_fields or "state" in mapped_fields:
        return None
    for header in csv_headers:
        normalized = _normalize_header(header)
        if normalized in LOCATION_HEADERS:
            return header
    return None


def _find_contact_person_column(csv_headers: list, column_mapping: dict) -> Optional[str]:
    """Find a contact person CSV column for company imports.

    Returns the CSV header name if found, None otherwise.
    """
    for header in csv_headers:
        normalized = _normalize_header(header)
        if normalized in CONTACT_PERSON_HEADERS and header not in column_mapping:
            return header
    return None


def _normalize_header(header: str) -> str:
    """Normalize a CSV header for matching: lowercase, strip, remove special chars."""
    return re.sub(r"[^a-z0-9]", "", header.lower().strip())


def _map_columns(csv_headers: List[str], target_fields: List[str]) -> Dict[str, str]:
    """Map CSV headers to target field names using exact match, aliases, and fuzzy matching.

    Returns dict of {csv_header: target_field} for matched columns.
    """
    mapping: Dict[str, str] = {}
    matched_fields: Set[str] = set()
    normalized_targets = {_normalize_header(f): f for f in target_fields}

    for header in csv_headers:
        normalized = _normalize_header(header)
        if not normalized:
            continue

        # 1. Exact match (after normalization)
        if normalized in normalized_targets and normalized_targets[normalized] not in matched_fields:
            mapping[header] = normalized_targets[normalized]
            matched_fields.add(normalized_targets[normalized])
            continue

        # 2. Alias lookup
        if normalized in COLUMN_ALIASES and COLUMN_ALIASES[normalized] in target_fields and COLUMN_ALIASES[normalized] not in matched_fields:
            mapping[header] = COLUMN_ALIASES[normalized]
            matched_fields.add(COLUMN_ALIASES[normalized])
            continue

        # 3. Fuzzy match as fallback
        best_score = 0.0
        best_field = None
        for target in target_fields:
            if target in matched_fields:
                continue
            score = SequenceMatcher(None, normalized, _normalize_header(target)).ratio()
            if score > best_score:
                best_score = score
                best_field = target
        if best_field and best_score >= FUZZY_MATCH_THRESHOLD:
            mapping[header] = best_field
            matched_fields.add(best_field)

    return mapping


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
        "description", "status",
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
        contact_decisions: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Import companies with optional auto-creation of linked contacts.

        contact_decisions: list of {csv_name, action, contact_id?} where action is
        "create_new", "link_existing", or "skip".
        """
        reader = csv.DictReader(io.StringIO(csv_content))
        csv_headers = reader.fieldnames or []

        column_mapping = _map_columns(csv_headers, self.COMPANY_FIELDS)
        name_col = _find_name_column(csv_headers, column_mapping, self.COMPANY_FIELDS)
        location_col = _find_location_column(csv_headers, column_mapping, self.COMPANY_FIELDS)
        contact_person_col = _find_contact_person_column(csv_headers, column_mapping)

        # Build lookup for contact decisions: csv_name -> {action, contact_id}
        decision_map: Dict[str, Dict[str, Any]] = {}
        if contact_decisions:
            for d in contact_decisions:
                decision_map[d["csv_name"].strip().lower()] = d

        existing_emails = await self._get_existing_emails(Company)
        seen_emails: Set[str] = set()

        imported = 0
        contacts_created = 0
        contacts_linked = 0
        errors = []
        duplicates_skipped = 0
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
                        first, last = _split_full_name(raw_name)
                        entity_data["first_name"] = first
                        entity_data["last_name"] = last

                if location_col:
                    raw_loc = row.get(location_col, "").strip()
                    if raw_loc:
                        city, state = _split_location(raw_loc)
                        entity_data["city"] = city
                        entity_data["state"] = state

                # Duplicate detection
                email = (entity_data.get("email") or "").lower()
                if email:
                    if email in existing_emails or email in seen_emails:
                        duplicates_skipped += 1
                        errors.append(f"Row {row_num}: skipped duplicate email '{email}'")
                        continue
                    seen_emails.add(email)

                company = Company(**entity_data, owner_id=user_id, created_by_id=user_id)
                self.db.add(company)

                if skip_errors:
                    try:
                        await self.db.flush()
                        imported += 1
                    except Exception as flush_exc:
                        await self.db.rollback()
                        errors.append(f"Row {row_num}: {str(flush_exc)}")
                        continue
                else:
                    await self.db.flush()
                    imported += 1

                # Auto-create or link contacts from Point of Contact column
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
                                # Link existing contact to this company
                                from sqlalchemy import update
                                await self.db.execute(
                                    update(Contact)
                                    .where(Contact.id == decision["contact_id"])
                                    .values(company_id=company.id)
                                )
                                contacts_linked += 1
                            else:
                                # Create new contact linked to this company
                                first, last = _split_full_name(contact_name)
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
                                    errors.append(f"Row {row_num}: contact '{contact_name}': {str(contact_exc)}")

            except Exception as e:
                errors.append(f"Row {row_num}: {str(e)}")
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
        }

    async def import_leads(self, csv_content: str, user_id: int, skip_errors: bool = True) -> Dict[str, Any]:
        return await self._import_entities(csv_content, Lead, self.LEAD_FIELDS, user_id, skip_errors)

    # ------------------------------------------------------------------
    # Preview (no DB writes)
    # ------------------------------------------------------------------

    async def preview_csv(self, entity_type: str, csv_content: str) -> Dict[str, Any]:
        """Preview a CSV: show column mapping, first rows, and validation warnings."""
        fields = self._get_fields(entity_type)
        reader = csv.DictReader(io.StringIO(csv_content))
        csv_headers = reader.fieldnames or []

        column_mapping = _map_columns(csv_headers, fields)
        name_col = _find_name_column(csv_headers, column_mapping, fields)
        location_col = _find_location_column(csv_headers, column_mapping, fields)
        contact_person_col = _find_contact_person_column(csv_headers, column_mapping) if entity_type == "companies" else None
        special_cols = {name_col, location_col, contact_person_col} - {None}
        unmapped = [h for h in csv_headers if h not in column_mapping and h not in special_cols]
        missing_fields = [f for f in fields if f not in column_mapping.values()]
        if name_col:
            missing_fields = [f for f in missing_fields if f not in ("first_name", "last_name")]
        if location_col:
            missing_fields = [f for f in missing_fields if f not in ("city", "state")]

        # Load existing contacts for fuzzy matching during company import
        existing_contacts = []
        if contact_person_col:
            result = await self.db.execute(
                select(Contact.id, Contact.first_name, Contact.last_name, Contact.email, Contact.company_id)
            )
            existing_contacts = result.all()

        # Read ALL rows to collect contact person names and build matches
        all_rows_raw = list(csv.DictReader(io.StringIO(csv_content)))
        total_rows = len(all_rows_raw)

        # Read first 5 rows with mapped column names
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
                    first, last = _split_full_name(raw_name)
                    mapped_row["first_name"] = first
                    mapped_row["last_name"] = last
            if location_col:
                raw_loc = row.get(location_col, "").strip()
                if raw_loc:
                    city, state = _split_location(raw_loc)
                    mapped_row["city"] = city
                    mapped_row["state"] = state

            if i < 5:
                preview_rows.append(mapped_row)

            # Check for duplicate emails within file
            email = mapped_row.get("email", "").lower()
            if email:
                if email in emails_seen:
                    warnings.append(f"Row {i + 2}: duplicate email '{email}' within file")
                emails_seen.add(email)

            # Build contact match candidates for company imports
            if contact_person_col:
                raw_contact = row.get(contact_person_col, "").strip()
                if raw_contact:
                    # Handle multiple contacts separated by comma (e.g. "Marco Russo, Anna Russo")
                    contact_names = [n.strip() for n in raw_contact.split(",") if n.strip()]
                    for contact_name in contact_names:
                        first, last = _split_full_name(contact_name)
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

        result = {
            "total_rows": total_rows,
            "column_mapping": column_mapping,
            "unmapped_columns": unmapped,
            "missing_fields": missing_fields,
            "preview_rows": preview_rows,
            "warnings": warnings,
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

    async def _get_existing_emails(self, entity_class: Type) -> Set[str]:
        """Fetch all existing emails for an entity type to detect duplicates."""
        if not hasattr(entity_class, "email"):
            return set()
        result = await self.db.execute(
            select(func.lower(entity_class.email)).where(entity_class.email.isnot(None))
        )
        return {row[0] for row in result.all()}

    def _parse_value(self, field: str, raw: str) -> Any:
        """Parse a raw CSV string value to the appropriate Python type."""
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
    ) -> Dict[str, Any]:
        reader = csv.DictReader(io.StringIO(csv_content))
        csv_headers = reader.fieldnames or []

        # Smart column mapping
        column_mapping = _map_columns(csv_headers, fields)
        name_col = _find_name_column(csv_headers, column_mapping, fields)
        location_col = _find_location_column(csv_headers, column_mapping, fields)

        # Load existing emails for dedup
        existing_emails = await self._get_existing_emails(entity_class)
        seen_emails: Set[str] = set()

        imported = 0
        errors = []
        duplicates_skipped = 0
        row_num = 1

        for row in reader:
            row_num += 1
            try:
                entity_data = {}
                for csv_col, target_field in column_mapping.items():
                    raw = row.get(csv_col, "")
                    if raw:
                        entity_data[target_field] = self._parse_value(target_field, raw)

                # Split full name column into first_name + last_name
                if name_col:
                    raw_name = row.get(name_col, "").strip()
                    if raw_name:
                        first, last = _split_full_name(raw_name)
                        entity_data["first_name"] = first
                        entity_data["last_name"] = last

                # Split location column into city + state
                if location_col:
                    raw_loc = row.get(location_col, "").strip()
                    if raw_loc:
                        city, state = _split_location(raw_loc)
                        entity_data["city"] = city
                        entity_data["state"] = state

                # Duplicate detection by email
                email = (entity_data.get("email") or "").lower()
                if email:
                    if email in existing_emails or email in seen_emails:
                        duplicates_skipped += 1
                        errors.append(f"Row {row_num}: skipped duplicate email '{email}'")
                        continue
                    seen_emails.add(email)

                entity = entity_class(**entity_data, owner_id=user_id, created_by_id=user_id)
                self.db.add(entity)

                if skip_errors:
                    try:
                        await self.db.flush()
                        imported += 1
                    except Exception as flush_exc:
                        await self.db.rollback()
                        errors.append(f"Row {row_num}: {str(flush_exc)}")
                else:
                    imported += 1

            except Exception as e:
                errors.append(f"Row {row_num}: {str(e)}")
                if not skip_errors:
                    await self.db.rollback()
                    return {"imported": 0, "errors": errors, "success": False, "duplicates_skipped": duplicates_skipped}

        if not skip_errors:
            await self.db.flush()

        return {
            "imported": imported,
            "errors": errors,
            "success": True,
            "duplicates_skipped": duplicates_skipped,
        }

    def get_template(self, entity_type: str) -> str:
        fields = self._get_fields(entity_type)
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        return output.getvalue()
