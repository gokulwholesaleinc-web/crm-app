"""Canonical entity-type names shared by polymorphic CRM endpoints."""

ENTITY_PLURALS = {
    "contact": "contacts",
    "company": "companies",
    "lead": "leads",
    "opportunity": "opportunities",
    "proposal": "proposals",
    "quote": "quotes",
    "contract": "contracts",
    "payment": "payments",
    "activity": "activities",
    "expense": "expenses",
    "campaign": "campaigns",
}

ENTITY_SINGULARS = {
    plural: singular for singular, plural in ENTITY_PLURALS.items()
}


def canonical_singular(entity_type: str) -> str:
    """Return the canonical singular form of an entity type input."""
    lower = entity_type.lower()
    if lower in ENTITY_PLURALS:
        return lower
    if lower in ENTITY_SINGULARS:
        return ENTITY_SINGULARS[lower]
    return lower


def canonical_plural(entity_type: str) -> str:
    """Return the canonical plural form used by EntityShare/DataScope."""
    singular = canonical_singular(entity_type)
    return ENTITY_PLURALS.get(singular, singular)


def entity_type_variants(entity_type: str) -> set[str]:
    """Return raw, singular, and plural forms used by historical share rows."""
    lower = entity_type.lower()
    return {lower, canonical_singular(lower), canonical_plural(lower)}
