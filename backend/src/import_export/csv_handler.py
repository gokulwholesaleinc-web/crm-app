"""CSV import/export handler with smart column mapping and duplicate detection."""

import csv
import io
import logging
from collections.abc import Sequence
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.companies.models import Company
from src.contacts.models import Contact
from src.dedup.service import normalize_phone
from src.import_export.csv_column_mapper import (
    apply_monday_status,
    detect_linkedin_format,
    detect_monday_csv,
    find_contact_person_column,
    find_location_column,
    find_name_column,
    map_columns,
    normalize_header,
    split_full_name,
    split_location,
)
from src.leads.models import Lead

logger = logging.getLogger(__name__)

MatchKey = Literal["none", "email", "phone", "name_plus_company"]
MergeStrategy = Literal["preserve_existing", "overwrite_all"]
ALLOWED_MATCH_KEYS: tuple[str, ...] = ("none", "email", "phone", "name_plus_company")
ALLOWED_MERGE_STRATEGIES: tuple[str, ...] = ("preserve_existing", "overwrite_all")

# Fields the import pipeline must never overwrite on an existing row — the
# AuditableMixin owns created_at / created_by_id, and ownership is set by
# explicit reassign flows, never by an upload.
PROTECTED_FIELDS_ON_MERGE: frozenset[str] = frozenset(
    {"id", "created_at", "created_by_id", "owner_id", "deleted_at", "merged_into_id"}
)

# Re-export module-level helpers so callers that imported them from here still work
__all__ = [
    "CSVHandler",
    "MatchKey",
    "MergeStrategy",
    "ALLOWED_MATCH_KEYS",
    "ALLOWED_MERGE_STRATEGIES",
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


def _format_match_value(value: Any) -> str:
    """Serialize a match-index key for inclusion in API responses."""
    if isinstance(value, tuple):
        # name_plus_company: keep human-readable; the company_id is just an
        # int marker and a missing one shows as "—" so the wizard can call
        # out rows without company context.
        first, last, company_id, company_name = value
        bits = [f"{first} {last}".strip() or "—"]
        if company_name:
            bits.append(company_name)
        elif company_id:
            bits.append(f"company#{company_id}")
        else:
            bits.append("—")
        return " · ".join(bits)
    return str(value) if value is not None else ""


def _entity_type_for(entity_class: type) -> str:
    """Map ORM class to the entity_type slug AuditService expects."""
    return {
        Contact: "contacts",
        Company: "companies",
        Lead: "leads",
    }.get(entity_class, getattr(entity_class, "__tablename__", entity_class.__name__.lower()))

# Legacy private-name aliases — tests/unit/test_import_export.py and
# tests/unit/test_linkedin_campaigns.py still import these
_map_columns = map_columns
_normalize_header = normalize_header
_split_full_name = split_full_name
_find_name_column = find_name_column


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

    def _get_fields(self, entity_type: str) -> list[str]:
        return {"contacts": self.CONTACT_FIELDS, "companies": self.COMPANY_FIELDS, "leads": self.LEAD_FIELDS}[entity_type]

    def _get_model(self, entity_type: str) -> type:
        return {"contacts": Contact, "companies": Company, "leads": Lead}[entity_type]

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    async def export_contacts(self, user_id: int | None = None) -> str:
        query = select(Contact)
        if user_id:
            query = query.where(Contact.owner_id == user_id)
        result = await self.db.execute(query)
        return self._to_csv(result.scalars().all(), self.CONTACT_FIELDS)

    async def export_companies(self, user_id: int | None = None) -> str:
        query = select(Company)
        if user_id:
            query = query.where(Company.owner_id == user_id)
        result = await self.db.execute(query)
        return self._to_csv(result.scalars().all(), self.COMPANY_FIELDS)

    async def export_leads(self, user_id: int | None = None) -> str:
        query = select(Lead)
        if user_id:
            query = query.where(Lead.owner_id == user_id)
        result = await self.db.execute(query)
        return self._to_csv(result.scalars().all(), self.LEAD_FIELDS)

    # ------------------------------------------------------------------
    # Import
    # ------------------------------------------------------------------

    async def import_contacts(
        self,
        csv_content: str,
        user_id: int,
        skip_errors: bool = True,
        match_key: str = "none",
        merge_strategy: str = "preserve_existing",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        return await self._import_entities(
            csv_content,
            Contact,
            self.CONTACT_FIELDS,
            user_id,
            skip_errors,
            match_key=match_key,
            merge_strategy=merge_strategy,
            dry_run=dry_run,
        )

    async def import_companies(
        self,
        csv_content: str,
        user_id: int,
        skip_errors: bool = True,
        contact_decisions: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Import companies with optional auto-creation of linked contacts."""
        reader = csv.DictReader(io.StringIO(csv_content))
        csv_headers = reader.fieldnames or []

        column_mapping = map_columns(csv_headers, self.COMPANY_FIELDS)
        name_col = find_name_column(csv_headers, column_mapping, self.COMPANY_FIELDS)
        location_col = find_location_column(csv_headers, column_mapping, self.COMPANY_FIELDS)
        contact_person_col = find_contact_person_column(csv_headers, column_mapping)

        decision_map: dict[str, dict[str, Any]] = {}
        if contact_decisions:
            for d in contact_decisions:
                decision_map[d["csv_name"].strip().lower()] = d

        existing_emails = await self._get_existing_emails(Company)
        existing_names = await self._get_existing_names(Company)
        seen_emails: set[str] = set()
        seen_names: set[str] = set()

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

    async def import_leads(
        self,
        csv_content: str,
        user_id: int,
        skip_errors: bool = True,
        match_key: str = "none",
        merge_strategy: str = "preserve_existing",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        return await self._import_entities(
            csv_content,
            Lead,
            self.LEAD_FIELDS,
            user_id,
            skip_errors,
            match_key=match_key,
            merge_strategy=merge_strategy,
            dry_run=dry_run,
        )

    # ------------------------------------------------------------------
    # Preview (no DB writes)
    # ------------------------------------------------------------------

    async def import_with_mapping(
        self,
        entity_type: str,
        csv_content: str,
        column_mapping: dict[str, str],
        user_id: int,
        skip_errors: bool = True,
        match_key: str = "none",
        merge_strategy: str = "preserve_existing",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Import entities using user-specified column mapping."""
        entity_class = self._get_model(entity_type)
        fields = self._get_fields(entity_type)

        for _csv_col, target_field in column_mapping.items():
            if target_field not in fields and target_field not in ("skip", ""):
                raise ValueError(f"Invalid target field '{target_field}' for {entity_type}")

        active_mapping = {k: v for k, v in column_mapping.items() if v and v != "skip"}

        return await self._import_entities(
            csv_content,
            entity_class,
            fields,
            user_id,
            skip_errors,
            active_mapping,
            match_key=match_key,
            merge_strategy=merge_strategy,
            dry_run=dry_run,
        )

    async def preview_csv(self, entity_type: str, csv_content: str) -> dict[str, Any]:
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
        emails_seen: set[str] = set()
        contact_matches: list[dict[str, Any]] = []

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

    def _to_csv(self, entities: Sequence[Any], fields: list[str]) -> str:
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

    async def _get_existing_names(self, entity_class: type) -> set[str]:
        if not hasattr(entity_class, "name"):
            return set()
        result = await self.db.execute(
            select(func.lower(entity_class.name)).where(entity_class.name.isnot(None))
        )
        return {row[0] for row in result.all()}

    async def _get_existing_emails(self, entity_class: type) -> set[str]:
        if not hasattr(entity_class, "email"):
            return set()
        result = await self.db.execute(
            select(func.lower(entity_class.email)).where(entity_class.email.isnot(None))
        )
        return {row[0] for row in result.all()}

    @staticmethod
    def _row_match_value(entity_data: dict[str, Any], match_key: str) -> str | tuple | None:
        """Pull the comparable match value out of a parsed CSV row.

        Returns ``None`` when the row has no usable value for the chosen
        match key — the import path should treat that row as a brand new
        record rather than guessing.
        """
        if match_key == "email":
            email = entity_data.get("email")
            return email.lower().strip() if isinstance(email, str) and email.strip() else None
        if match_key == "phone":
            phone = entity_data.get("phone")
            normalized = normalize_phone(phone) if isinstance(phone, str) else ""
            return normalized or None
        if match_key == "name_plus_company":
            first = (entity_data.get("first_name") or "").strip().lower()
            last = (entity_data.get("last_name") or "").strip().lower()
            if not (first and last):
                return None
            company_id = entity_data.get("company_id")
            company_name = (entity_data.get("company_name") or "").strip().lower()
            return (first, last, company_id, company_name or None)
        return None

    @staticmethod
    def _entity_match_value(entity: Any, match_key: str) -> str | tuple | None:
        """Same as ``_row_match_value`` but reads from a hydrated ORM entity."""
        if match_key == "email":
            email = getattr(entity, "email", None)
            return email.lower().strip() if isinstance(email, str) and email.strip() else None
        if match_key == "phone":
            phone = getattr(entity, "phone", None)
            normalized = normalize_phone(phone) if isinstance(phone, str) else ""
            return normalized or None
        if match_key == "name_plus_company":
            first = (getattr(entity, "first_name", None) or "").strip().lower()
            last = (getattr(entity, "last_name", None) or "").strip().lower()
            if not (first and last):
                return None
            company_id = getattr(entity, "company_id", None)
            company_name = (getattr(entity, "company_name", None) or "").strip().lower()
            return (first, last, company_id, company_name or None)
        return None

    async def _build_match_index(
        self, entity_class: type, match_key: str
    ) -> dict[Any, list[int]]:
        """Build a single-query lookup index of existing rows by match key.

        Maps the comparable key (lower email, normalized phone, or composite
        tuple) to the list of existing entity ids that produce that key. We
        return *lists* rather than ids so the caller can flag conflict rows
        (one CSV row landing on multiple existing records) instead of
        silently merging into the first match.

        Soft-deleted rows and merged-away rows are filtered out — those
        records still exist for AR-ledger / audit-history reasons (see the
        ``deleted_at IS NULL`` invariant documented on
        :class:`src.contacts.models.Contact`) but they MUST NOT be the
        target of a re-import update or the merged-away row would silently
        come back to life. Mirrored on the per-row re-fetch in
        :meth:`_merge_into_existing` as a belt-and-suspenders guard.
        """
        if match_key == "none":
            return {}
        query = select(entity_class)
        if hasattr(entity_class, "deleted_at"):
            query = query.where(entity_class.deleted_at.is_(None))
        if hasattr(entity_class, "merged_into_id"):
            query = query.where(entity_class.merged_into_id.is_(None))
        result = await self.db.execute(query)
        index: dict[Any, list[int]] = {}
        for entity in result.scalars().all():
            key = self._entity_match_value(entity, match_key)
            if key is None:
                continue
            index.setdefault(key, []).append(entity.id)
        return index

    @staticmethod
    def _diff_fields(
        existing: Any,
        new_data: dict[str, Any],
        strategy: str,
    ) -> list[dict[str, Any]]:
        """Compute the list of field changes a merge would apply.

        Each diff dict is shaped to match :class:`src.audit.service.AuditService`
        ``log_change`` expectations (``field`` / ``old`` / ``new``) so the dry-
        run preview and the executed merge produce identical change records.
        """
        diffs: list[dict[str, Any]] = []
        for field, new_value in new_data.items():
            if field in PROTECTED_FIELDS_ON_MERGE:
                continue
            old_value = getattr(existing, field, None)
            if strategy == "preserve_existing":
                # Only fill blanks. None, "" and 0/0.0 are treated as
                # blank — the CSV importer never writes a zero into a
                # numeric field unless it parsed something, and a literal
                # 0 in budget_amount is conceptually empty.
                blank = old_value is None or (isinstance(old_value, str) and not old_value.strip())
                if not blank:
                    continue
            if old_value == new_value:
                continue
            diffs.append({"field": field, "old": old_value, "new": new_value})
        return diffs

    @staticmethod
    def _apply_diffs(existing: Any, diffs: list[dict[str, Any]]) -> None:
        """Apply a precomputed diff list to an entity in-place."""
        for diff in diffs:
            setattr(existing, diff["field"], diff["new"])

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
        entity_class: type,
        fields: list[str],
        user_id: int,
        skip_errors: bool = True,
        column_mapping: dict[str, str] | None = None,
        match_key: str = "none",
        merge_strategy: str = "preserve_existing",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        if match_key not in ALLOWED_MATCH_KEYS:
            raise ValueError(f"Invalid match_key '{match_key}'. Allowed: {ALLOWED_MATCH_KEYS}")
        if merge_strategy not in ALLOWED_MERGE_STRATEGIES:
            raise ValueError(
                f"Invalid merge_strategy '{merge_strategy}'. Allowed: {ALLOWED_MERGE_STRATEGIES}"
            )

        reader = csv.DictReader(io.StringIO(csv_content))
        csv_headers = reader.fieldnames or []

        if column_mapping is None:
            column_mapping = map_columns(csv_headers, fields)
        name_col = find_name_column(csv_headers, column_mapping, fields)
        location_col = find_location_column(csv_headers, column_mapping, fields)
        is_monday = detect_monday_csv(csv_headers)
        is_linkedin = detect_linkedin_format(csv_headers)

        existing_emails = await self._get_existing_emails(entity_class)
        match_index = await self._build_match_index(entity_class, match_key)
        seen_emails: set[str] = set()
        # Track which CSV row claimed which existing id so two rows can't
        # both try to merge into the same existing record on this pass.
        claimed_ids: set[int] = set()

        imported = 0
        updated_count = 0
        updates: list[dict[str, Any]] = []
        conflicts: list[dict[str, Any]] = []
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

                # Reconcile against existing rows if a match_key was chosen.
                match_value = self._row_match_value(entity_data, match_key) if match_key != "none" else None
                if match_value is not None:
                    candidate_ids = match_index.get(match_value, [])
                    if len(candidate_ids) > 1:
                        conflicts.append({
                            "row": row_num,
                            "match_key": match_key,
                            "match_value": _format_match_value(match_value),
                            "existing_ids": list(candidate_ids),
                            "reason": "Multiple existing records match this key",
                        })
                        continue
                    if len(candidate_ids) == 1:
                        existing_id = candidate_ids[0]
                        if existing_id in claimed_ids:
                            conflicts.append({
                                "row": row_num,
                                "match_key": match_key,
                                "match_value": _format_match_value(match_value),
                                "existing_ids": [existing_id],
                                "reason": "Another row in this file already matched this record",
                            })
                            continue
                        claimed_ids.add(existing_id)
                        update_result, conflict = await self._merge_into_existing(
                            entity_class=entity_class,
                            existing_id=existing_id,
                            entity_data=entity_data,
                            row_num=row_num,
                            match_key=match_key,
                            match_value=match_value,
                            merge_strategy=merge_strategy,
                            user_id=user_id,
                            dry_run=dry_run,
                        )
                        if conflict is not None:
                            conflicts.append(conflict)
                        elif update_result is not None:
                            updates.append(update_result)
                            updated_count += 1
                        continue

                # Legacy email-skip dedup only fires when no match key is
                # set — with a match key we already covered the email path
                # via the reconcile branch above.
                email = (entity_data.get("email") or "").lower()
                if match_key == "none" and email:
                    if email in existing_emails or email in seen_emails:
                        duplicates_skipped += 1
                        first = entity_data.get("first_name") or ""
                        last = entity_data.get("last_name") or ""
                        label = f"{first} {last}".strip()
                        label = label or entity_data.get("company_name") or entity_data.get("name") or ""
                        duplicates.append({"row": row_num, "email": email, "label": label})
                        continue
                    seen_emails.add(email)

                if dry_run:
                    imported += 1
                    continue

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
                    return {
                        "imported": 0,
                        "errors": errors,
                        "success": False,
                        "duplicates_skipped": duplicates_skipped,
                        "updated_count": updated_count,
                        "updates": updates,
                        "conflicts": conflicts,
                    }

        if not skip_errors and not dry_run:
            await self.db.flush()
        # No dry-run rollback: `_merge_into_existing` short-circuits before
        # mutating any entity when `dry_run=True`, and a rollback here
        # would also discard unrelated pending state from a future caller
        # that composes this method with other DB writes in the same
        # session (FastAPI commits on request exit via `get_db`).

        return {
            "imported": imported,
            "errors": errors,
            "success": True,
            "duplicates_skipped": duplicates_skipped,
            "duplicates": duplicates,
            "updated_count": updated_count,
            "updates": updates,
            "conflicts": conflicts,
            "dry_run": dry_run,
        }

    async def _merge_into_existing(
        self,
        *,
        entity_class: type,
        existing_id: int,
        entity_data: dict[str, Any],
        row_num: int,
        match_key: str,
        match_value: Any,
        merge_strategy: str,
        user_id: int,
        dry_run: bool,
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        """Merge ``entity_data`` into the existing row identified by ``existing_id``.

        Returns a ``(update, conflict)`` pair so the caller can record the
        outcome accurately:

        - ``(update, None)`` — merge applied (or planned, in dry-run).
        - ``(None, conflict)`` — the row vanished between index build and
          re-fetch (got soft-deleted or merged away mid-import). A real
          conflict entry lets the user see the row was dropped instead of
          silently losing it.
        """
        query = select(entity_class).where(entity_class.id == existing_id)
        if hasattr(entity_class, "deleted_at"):
            query = query.where(entity_class.deleted_at.is_(None))
        if hasattr(entity_class, "merged_into_id"):
            query = query.where(entity_class.merged_into_id.is_(None))
        result = await self.db.execute(query)
        existing = result.scalar_one_or_none()
        if existing is None:
            logger.warning(
                "import dedup: existing_id=%s vanished or was soft-deleted between index build and merge",
                existing_id,
            )
            return None, {
                "row": row_num,
                "match_key": match_key,
                "match_value": _format_match_value(match_value),
                "existing_ids": [existing_id],
                "reason": "Existing record was deleted or merged during import",
            }

        diffs = self._diff_fields(existing, entity_data, merge_strategy)
        summary = {
            "row": row_num,
            "existing_id": existing_id,
            "match_key": match_key,
            "match_value": _format_match_value(match_value),
            "merge_strategy": merge_strategy,
            "field_changes": diffs,
            "noop": len(diffs) == 0,
        }
        if dry_run or not diffs:
            return summary, None

        self._apply_diffs(existing, diffs)
        existing.updated_by_id = user_id

        # Audit log mirrors what the existing /api/dedup/merge writes, so
        # an import-time field fill shows up on the entity history page
        # alongside ordinary edits. Wrap in a SAVEPOINT so an audit-table
        # failure can't leave the outer session in PendingRollbackError —
        # a correct merge must survive a flaky audit insert.
        try:
            from src.audit.service import AuditService
            async with self.db.begin_nested():
                audit = AuditService(self.db)
                entity_type = _entity_type_for(entity_class)
                await audit.log_change(
                    entity_type=entity_type,
                    entity_id=existing_id,
                    user_id=user_id,
                    action="import_merge",
                    changes=diffs,
                )
        except Exception:
            # Audit failure must not roll back a correct merge. Capture the
            # traceback so Sentry can pick it up instead of dropping the
            # context with %s.
            logger.exception(
                "import dedup: failed to audit merge for %s id=%s row=%s",
                entity_class.__name__, existing_id, row_num,
            )

        return summary, None

    def get_template(self, entity_type: str) -> str:
        fields = self._get_fields(entity_type)
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        return output.getvalue()
