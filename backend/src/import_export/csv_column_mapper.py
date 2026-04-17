"""CSV column mapping utilities: aliases, normalization, fuzzy matching, and format detection."""

import re
from difflib import SequenceMatcher

# Common aliases for CSV columns → internal field names
COLUMN_ALIASES: dict[str, str] = {
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
    "location": "address_line1",
    "address2": "address_line2",
    "zip": "postal_code",
    "zipcode": "postal_code",
    "zip_code": "postal_code",
    "postcode": "postal_code",
    "linkedin": "linkedin_url",
    # Business size aliases
    "businesssizetier": "company_size",
    "businesssize": "company_size",
    "companytier": "company_size",
    "sizetier": "company_size",
    "tier": "company_size",
    # Link Creative Tier aliases
    "linkcreativetier": "link_creative_tier",
    "creativetier": "link_creative_tier",
    "linktier": "link_creative_tier",
    # SOW aliases
    "sow": "sow_url",
    "sowurl": "sow_url",
    "statementofwork": "sow_url",
    # Account Manager aliases
    "accountmanager": "account_manager",
    "am": "account_manager",
    "manager": "account_manager",
}

# Headers that represent a full name (to be split into first_name + last_name)
FULL_NAME_HEADERS = {"name", "fullname", "person", "contactname", "leadname"}

# Headers that represent a combined location (to be split into city + state)
LOCATION_HEADERS = {"hqlocation", "hqaddress", "headquarterslocation", "headquarters", "cityst", "citystate"}

# Headers that represent a contact person name (for auto-creating linked contacts on company import)
CONTACT_PERSON_HEADERS = {"pointofcontact", "poc", "contactperson", "primarycontact", "contactname", "contact"}

FUZZY_MATCH_THRESHOLD = 0.75

# Monday.com status label → CRM lead status mapping
MONDAY_STATUS_MAP: dict[str, str] = {
    "working on it": "contacted",
    "done": "converted",
    "stuck": "unqualified",
    "not started": "new",
}

# Monday.com-specific column headers used for CSV source detection
_MONDAY_SIGNATURE_HEADERS = {"subitems", "lastupdated", "creationlog", "itemid", "linkedpulses", "mirrorcolumn", "peoplecolumn"}

# LinkedIn Sales Navigator CSV signature headers
_LINKEDIN_SIGNATURE_HEADERS = {
    "firstname", "lastname", "company", "title", "linkedinprofileurl",
    "email", "geography", "industry", "connectiondegree", "connected",
}

# Headers unique to LinkedIn exports (not common in generic CSVs)
_LINKEDIN_UNIQUE_HEADERS = {"linkedinprofileurl", "connectiondegree", "connected", "geography"}


def normalize_header(header: str) -> str:
    """Normalize a CSV header for matching: lowercase, strip, remove special chars."""
    return re.sub(r"[^a-z0-9]", "", header.lower().strip())


def detect_linkedin_format(headers: list) -> bool:
    """Return True if the CSV headers match LinkedIn Sales Navigator export format."""
    normalized = {normalize_header(h) for h in headers}
    matched = normalized & _LINKEDIN_SIGNATURE_HEADERS
    has_unique = bool(normalized & _LINKEDIN_UNIQUE_HEADERS)
    return len(matched) >= 4 and has_unique


def detect_monday_csv(csv_headers: list[str]) -> bool:
    """Return True if the CSV headers contain Monday.com-specific columns."""
    normalized = {normalize_header(h) for h in csv_headers}
    return len(normalized & _MONDAY_SIGNATURE_HEADERS) >= 2


def apply_monday_status(value: str) -> str:
    """Convert a Monday.com status label to a CRM lead status, falling back to the original value."""
    return MONDAY_STATUS_MAP.get(value.strip().lower(), value)


def split_full_name(full_name: str) -> tuple:
    """Split 'John Smith' into ('John', 'Smith')."""
    parts = full_name.strip().split(None, 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return (parts[0], "") if parts else ("", "")


def split_location(location: str) -> tuple:
    """Split 'Springfield, IL' into ('Springfield', 'IL')."""
    parts = [p.strip() for p in location.strip().split(",", 1)]
    if len(parts) == 2:
        return parts[0], parts[1]
    return (parts[0], "") if parts else ("", "")


def find_name_column(csv_headers: list, column_mapping: dict, target_fields: list):
    """Find a full-name CSV column that should be split into first_name + last_name."""
    if "first_name" not in target_fields or "last_name" not in target_fields:
        return None
    mapped_fields = set(column_mapping.values())
    if "first_name" in mapped_fields or "last_name" in mapped_fields:
        return None
    for header in csv_headers:
        if normalize_header(header) in FULL_NAME_HEADERS:
            return header
    return None


def find_location_column(csv_headers: list, column_mapping: dict, target_fields: list):
    """Find a combined location CSV column that should be split into city + state."""
    if "city" not in target_fields or "state" not in target_fields:
        return None
    mapped_fields = set(column_mapping.values())
    if "city" in mapped_fields or "state" in mapped_fields:
        return None
    for header in csv_headers:
        if normalize_header(header) in LOCATION_HEADERS:
            return header
    return None


def find_contact_person_column(csv_headers: list, column_mapping: dict) -> str | None:
    """Find a contact person CSV column for company imports."""
    for header in csv_headers:
        if normalize_header(header) in CONTACT_PERSON_HEADERS and header not in column_mapping:
            return header
    return None


def map_columns(csv_headers: list[str], target_fields: list[str]) -> dict[str, str]:
    """Map CSV headers to target field names using exact match, aliases, and fuzzy matching."""
    mapping: dict[str, str] = {}
    matched_fields: set[str] = set()
    normalized_targets = {normalize_header(f): f for f in target_fields}

    for header in csv_headers:
        normalized = normalize_header(header)
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
            score = SequenceMatcher(None, normalized, normalize_header(target)).ratio()
            if score > best_score:
                best_score = score
                best_field = target
        if best_field and best_score >= FUZZY_MATCH_THRESHOLD:
            mapping[header] = best_field
            matched_fields.add(best_field)

    return mapping
