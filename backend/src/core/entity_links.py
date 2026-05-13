"""Shared helper for resolving polymorphic ``entity_type``/``entity_id``
references into display labels + frontend routes.

Activities, notifications, and (eventually) audit rows all carry an
opaque (entity_type, entity_id) tuple. The frontend wants a clickable
chip — a human-readable label + a URL prefix that maps to the entity
detail route. Centralizing this avoids drift between surfaces that
otherwise format the same kind of reference inconsistently.

Keep ``_ROUTABLE_ENTITY_PLURALS`` in sync with the frontend's
``frontend/src/routes/index.tsx`` route table — an entity type that
isn't routable here gets a label but no link.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

ROUTABLE_ENTITY_PLURALS: dict[str, str] = {
    "contacts": "/contacts",
    "companies": "/companies",
    "leads": "/leads",
    "opportunities": "/opportunities",
    "quotes": "/quotes",
    "proposals": "/proposals",
    "contracts": "/contracts",
    "payments": "/payments",
    # `notify_on_activity_due_soon` writes entity_type="activities" so
    # the notification bell needs to route those to the activities page.
    "activities": "/activities",
}

# Historical singular spellings stored on older rows. Maps to the
# canonical plural used by ``ROUTABLE_ENTITY_PLURALS``.
ENTITY_ALIASES: dict[str, str] = {
    "contact": "contacts",
    "company": "companies",
    "lead": "leads",
    "opportunity": "opportunities",
    "quote": "quotes",
    "proposal": "proposals",
    "contract": "contracts",
    "payment": "payments",
    "activity": "activities",
}


def canonical_plural(entity_type: str | None) -> str | None:
    """Resolve any entity_type variant (singular or plural) to the
    canonical plural used elsewhere. Returns None for unknown types."""
    if not entity_type:
        return None
    if entity_type in ROUTABLE_ENTITY_PLURALS:
        return entity_type
    return ENTITY_ALIASES.get(entity_type)


def fallback_label(entity_type: str, entity_id: int) -> str:
    """Return a fallback display label when the entity row is gone /
    not joinable. Strips a trailing 's' from the plural for a cleaner
    "Contact #42" presentation."""
    return f"{entity_type.rstrip('s').capitalize()} #{entity_id}"


async def labels_for(
    db: AsyncSession, entity_type: str, ids: set[int],
) -> dict[tuple[str, int], str]:
    """Return ``{(entity_type, id): label}`` for one type in one query.

    ``entity_type`` is the canonical plural. Each branch is a single
    batched SELECT; types without a branch return an empty dict and
    callers should fall back to :func:`fallback_label`.
    """
    if not ids:
        return {}

    if entity_type == "contacts":
        from src.contacts.models import Contact
        rows = await db.execute(
            select(Contact.id, Contact.first_name, Contact.last_name).where(
                Contact.id.in_(ids)
            )
        )
        return {
            (entity_type, row[0]): f"{row[1] or ''} {row[2] or ''}".strip() or f"Contact #{row[0]}"
            for row in rows.all()
        }
    if entity_type == "leads":
        from src.leads.models import Lead
        rows = await db.execute(
            select(Lead.id, Lead.first_name, Lead.last_name).where(Lead.id.in_(ids))
        )
        return {
            (entity_type, row[0]): f"{row[1] or ''} {row[2] or ''}".strip() or f"Lead #{row[0]}"
            for row in rows.all()
        }
    if entity_type == "opportunities":
        from src.opportunities.models import Opportunity
        rows = await db.execute(
            select(Opportunity.id, Opportunity.name).where(Opportunity.id.in_(ids))
        )
        return {(entity_type, row[0]): row[1] for row in rows.all()}
    if entity_type == "companies":
        from src.companies.models import Company
        rows = await db.execute(
            select(Company.id, Company.name).where(Company.id.in_(ids))
        )
        return {(entity_type, row[0]): row[1] for row in rows.all()}
    if entity_type == "quotes":
        from src.quotes.models import Quote
        rows = await db.execute(
            select(Quote.id, Quote.quote_number).where(Quote.id.in_(ids))
        )
        return {(entity_type, row[0]): row[1] for row in rows.all()}
    if entity_type == "proposals":
        from src.proposals.models import Proposal
        rows = await db.execute(
            select(Proposal.id, Proposal.title).where(Proposal.id.in_(ids))
        )
        return {(entity_type, row[0]): row[1] for row in rows.all()}
    if entity_type == "contracts":
        from src.contracts.models import Contract
        rows = await db.execute(
            select(Contract.id, Contract.title).where(Contract.id.in_(ids))
        )
        return {(entity_type, row[0]): row[1] for row in rows.all()}
    if entity_type == "activities":
        from src.activities.models import Activity
        rows = await db.execute(
            select(Activity.id, Activity.subject, Activity.activity_type).where(
                Activity.id.in_(ids)
            )
        )
        # Fall back to the activity_type when no subject is set (notes /
        # call-only rows often have empty subjects).
        return {
            (entity_type, row[0]): row[1] or row[2].capitalize() or f"Activity #{row[0]}"
            for row in rows.all()
        }

    return {}


async def fill_entity_labels(
    db: AsyncSession, items: list[dict[str, Any]],
) -> None:
    """Populate ``entity_label`` + ``entity_link`` on each item in place.

    Items must carry ``entity_type`` + ``entity_id`` keys; missing or
    unroutable types are left as None so the UI can fall back to a
    plain text rendering without a broken link.
    """
    ids_by_type: dict[str, set[int]] = defaultdict(set)
    for item in items:
        plural = canonical_plural(item.get("entity_type"))
        eid = item.get("entity_id")
        if plural and eid:
            ids_by_type[plural].add(eid)

    label_lookup: dict[tuple[str, int], str] = {}
    for plural, ids in ids_by_type.items():
        label_lookup.update(await labels_for(db, plural, ids))

    for item in items:
        plural = canonical_plural(item.get("entity_type"))
        eid = item.get("entity_id")
        if not (plural and eid):
            item.setdefault("entity_label", None)
            item.setdefault("entity_link", None)
            continue
        url_prefix = ROUTABLE_ENTITY_PLURALS[plural]
        item["entity_label"] = (
            label_lookup.get((plural, eid)) or fallback_label(plural, eid)
        )
        item["entity_link"] = f"{url_prefix}/{eid}"
