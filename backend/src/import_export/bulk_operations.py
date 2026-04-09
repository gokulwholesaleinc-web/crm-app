"""Bulk operations for mass updates and assignments."""

from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from sqlalchemy import select, update, delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from src.leads.models import Lead
from src.contacts.models import Contact
from src.companies.models import Company
from src.opportunities.models import Opportunity
from src.activities.models import Activity


# Map entity type strings to model classes
ENTITY_MODELS = {
    "leads": Lead,
    "contacts": Contact,
    "companies": Company,
    "opportunities": Opportunity,
    "activities": Activity,
}

# Fields that are allowed for bulk update per entity type
ALLOWED_UPDATE_FIELDS = {
    "leads": {"status", "owner_id", "source_id", "score"},
    "contacts": {"status", "owner_id", "company_id"},
    "companies": {"status", "owner_id"},
    "opportunities": {"pipeline_stage_id", "owner_id", "currency"},
    "activities": {"owner_id", "assigned_to_id", "is_completed", "priority"},
}


class BulkOperationsHandler:
    """Handles bulk update and assign operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def bulk_update(
        self,
        entity_type: str,
        entity_ids: List[int],
        updates: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Mass update entities of a given type.

        Returns summary of the operation.
        """
        model = ENTITY_MODELS.get(entity_type)
        if not model:
            return {"success": False, "error": f"Invalid entity type: {entity_type}", "updated": 0}

        allowed = ALLOWED_UPDATE_FIELDS.get(entity_type, set())
        filtered_updates = {k: v for k, v in updates.items() if k in allowed}

        if not filtered_updates:
            return {"success": False, "error": "No valid update fields provided", "updated": 0}

        if not entity_ids:
            return {"success": False, "error": "No entity IDs provided", "updated": 0}

        stmt = (
            update(model)
            .where(model.id.in_(entity_ids))
            .values(**filtered_updates)
        )
        result = await self.db.execute(stmt)
        await self.db.flush()

        return {
            "success": True,
            "updated": result.rowcount,
            "entity_type": entity_type,
            "updates_applied": filtered_updates,
        }

    async def bulk_assign(
        self,
        entity_type: str,
        entity_ids: List[int],
        owner_id: int,
    ) -> Dict[str, Any]:
        """Mass assign owner to entities."""
        model = ENTITY_MODELS.get(entity_type)
        if not model:
            return {"success": False, "error": f"Invalid entity type: {entity_type}", "updated": 0}

        if not hasattr(model, "owner_id"):
            return {"success": False, "error": f"{entity_type} does not support owner assignment", "updated": 0}

        if not entity_ids:
            return {"success": False, "error": "No entity IDs provided", "updated": 0}

        stmt = (
            update(model)
            .where(model.id.in_(entity_ids))
            .values(owner_id=owner_id)
        )
        result = await self.db.execute(stmt)
        await self.db.flush()

        return {
            "success": True,
            "updated": result.rowcount,
            "entity_type": entity_type,
            "owner_id": owner_id,
        }

    async def bulk_delete(
        self,
        entity_type: str,
        entity_ids: List[int],
    ) -> Dict[str, Any]:
        """Mass delete entities of a given type.

        For ``contacts`` this is routed through the soft-delete path
        (``deleted_at`` + ``status="archived"`` + email prefix) per
        project rule ``feedback_delete_sales_only.md`` — contacts anchor
        AR ledger, invoice, and activity history that must not be
        destroyed even in a bulk operation.

        For every other entity type the original hard-delete behavior
        is preserved. Returns a summary with ``success_count``,
        ``error_count``, and a per-ID ``errors`` list.
        """
        model = ENTITY_MODELS.get(entity_type)
        if not model:
            return {"success": False, "error": f"Invalid entity type: {entity_type}"}

        if not entity_ids:
            return {"success": False, "error": "No entity IDs provided"}

        # Find which IDs actually exist
        result = await self.db.execute(
            select(model.id).where(model.id.in_(entity_ids))
        )
        existing_ids = set(result.scalars().all())

        missing_ids = set(entity_ids) - existing_ids
        errors: list[dict] = [{"id": eid, "error": "Not found"} for eid in missing_ids]
        changed_ids: set[int] = set()

        if existing_ids:
            if entity_type == "contacts":
                # Soft-delete path: load each live contact and mark it
                # archived. A bulk UPDATE would be faster but we need
                # per-row ``id`` access to prefix the email correctly
                # and we want to skip rows that are already archived
                # (otherwise ``success_count`` would overstate the work
                # actually done).
                contacts_result = await self.db.execute(
                    select(Contact)
                    .where(Contact.id.in_(existing_ids))
                    .where(Contact.deleted_at.is_(None))
                )
                now = datetime.now(timezone.utc)
                for contact in contacts_result.scalars().all():
                    contact.deleted_at = now
                    contact.status = "archived"
                    if contact.email and not contact.email.startswith("archived-"):
                        contact.email = (f"archived-{contact.id}-" + contact.email)[:255]
                    changed_ids.add(contact.id)
                for skipped in existing_ids - changed_ids:
                    errors.append({"id": skipped, "error": "Already archived"})
            elif entity_type == "companies":
                # Mirror the single-delete router guard: block company
                # rows that still have contacts attached. Callers would
                # otherwise sneak around ``delete_company``'s 409.
                counts = await self.db.execute(
                    select(Contact.company_id, func.count(Contact.id))
                    .where(Contact.company_id.in_(existing_ids))
                    .group_by(Contact.company_id)
                )
                blocked = {cid: count for cid, count in counts.all() if count > 0}
                deletable = existing_ids - blocked.keys()
                if deletable:
                    await self.db.execute(
                        delete(Company).where(Company.id.in_(deletable))
                    )
                changed_ids = deletable
                for cid, count in blocked.items():
                    errors.append(
                        {"id": cid, "error": f"Has {count} contacts — reassign or delete contacts first"}
                    )
            else:
                # Hard-delete for non-contact/non-company entities —
                # preserves legacy behavior for leads/opportunities/
                # activities.
                await self.db.execute(
                    delete(model).where(model.id.in_(existing_ids))
                )
                changed_ids = existing_ids

        success_count = len(changed_ids)
        error_count = len(errors)

        await self.db.flush()

        return {
            "success": True,
            "entity_type": entity_type,
            "success_count": success_count,
            "error_count": error_count,
            "errors": errors,
        }
