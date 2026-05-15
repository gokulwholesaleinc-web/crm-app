"""Cross-entity access checks for polymorphic endpoints.

Notes, comments, activities, attachments, and audit logs all attach to
arbitrary entities via `entity_type` + `entity_id`. Before returning their
content to a caller, we need to verify the caller has access to the parent
entity — otherwise they can enumerate across users via ID guessing.
"""


from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import HTTPStatus
from src.core.data_scope import DataScope, check_record_access_or_shared

# Canonical singular → plural map. Must match the entity_type keys used by
# EntityShare rows and DataScope.shared_entity_ids (see core/constants.py
# ENTITY_TYPE_COMPANIES="companies", etc). A naive `normalized + "s"`
# produces "companys"/"opportunitys"/"activitys", which silently drops
# shared access for those entity types.
_ENTITY_PLURALS = {
    "contact": "contacts",
    "company": "companies",
    "lead": "leads",
    "opportunity": "opportunities",
    "proposal": "proposals",
    "contract": "contracts",
    "payment": "payments",
    "activity": "activities",
    "expense": "expenses",
    "campaign": "campaigns",
}

# Reverse map: plural -> singular. Used to canonicalise inputs like
# "opportunities" / "companies" — naive rstrip("s") would mangle these into
# "opportunitie" / "companie" and silently fall through every if-branch.
_ENTITY_SINGULARS = {plural: singular for singular, plural in _ENTITY_PLURALS.items()}


def canonical_singular(entity_type: str) -> str:
    """Return the canonical singular form of an entity type input.

    Accepts either singular ("contact") or plural ("contacts") forms.
    Unknown inputs are returned lowercased unchanged.
    """
    lower = entity_type.lower()
    if lower in _ENTITY_PLURALS:
        return lower
    if lower in _ENTITY_SINGULARS:
        return _ENTITY_SINGULARS[lower]
    return lower


# Backwards-compatible alias for the old private name. Internal callers in
# this module continue to import it; remove once those are migrated.
_canonical_singular = canonical_singular


async def _resolve_entity(db: AsyncSession, entity_type: str, entity_id: int):
    """Return (entity, entity_type_alias) or (None, entity_type_alias).

    Supports both singular and plural forms of entity_type so callers can
    pass either "contact" or "contacts".
    """
    normalized = _canonical_singular(entity_type)
    plural = _ENTITY_PLURALS.get(normalized, normalized)

    # Lazy imports to avoid circular dependencies.
    if normalized == "contact":
        from src.contacts.models import Contact
        model = Contact
    elif normalized == "company":
        from src.companies.models import Company
        model = Company
    elif normalized == "lead":
        from src.leads.models import Lead
        model = Lead
    elif normalized == "opportunity":
        from src.opportunities.models import Opportunity
        model = Opportunity
    elif normalized == "proposal":
        from src.proposals.models import Proposal
        model = Proposal
    elif normalized == "contract":
        from src.contracts.models import Contract
        model = Contract
    elif normalized == "payment":
        from src.payments.models import Payment
        model = Payment
    elif normalized == "activity":
        from src.activities.models import Activity
        model = Activity
    elif normalized == "campaign":
        from src.campaigns.models import Campaign
        model = Campaign
    elif normalized == "expense":
        # Expenses don't have owner_id; treat as 'parent is the company'.
        from src.expenses.models import Expense
        result = await db.execute(select(Expense).where(Expense.id == entity_id))
        expense = result.scalar_one_or_none()
        if expense is None:
            return None, plural
        from src.companies.models import Company
        company_result = await db.execute(
            select(Company).where(Company.id == expense.company_id)
        )
        return company_result.scalar_one_or_none(), plural
    else:
        # Unknown entity type — reject rather than silently allowing.
        return None, plural

    result = await db.execute(select(model).where(model.id == entity_id))
    return result.scalar_one_or_none(), plural


async def require_entity_access(
    db: AsyncSession,
    entity_type: str,
    entity_id: int,
    current_user,
    data_scope: DataScope,
) -> None:
    """Raise 403/404 unless the caller can access the referenced entity.

    Returns None on success. Used by notes/comments/activities/audit/attachment
    endpoints before they return polymorphic content.
    """
    # Admin/manager/superuser bypass.
    if data_scope.can_see_all():
        # Still need to confirm the entity exists — otherwise we silently
        # 200 for a missing entity, which is more confusing than correct.
        entity, _ = await _resolve_entity(db, entity_type, entity_id)
        if entity is None:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail=f"{entity_type} {entity_id} not found",
            )
        return

    entity, plural = await _resolve_entity(db, entity_type, entity_id)
    if entity is None:
        # Don't leak existence — treat missing or inaccessible the same.
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail=f"{entity_type} {entity_id} not found",
        )
    check_record_access_or_shared(
        entity,
        current_user,
        data_scope.role_name,
        shared_entity_ids=data_scope.get_shared_ids(plural),
        entity_type=plural,
    )
