"""Bulk operations for mass updates and assignments."""

from typing import List, Dict, Any, Optional
from sqlalchemy import select, update
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
        """Mass delete entities by ID."""
        model = ENTITY_MODELS.get(entity_type)
        if not model:
            return {"success": False, "error": f"Invalid entity type: {entity_type}"}

        if not entity_ids:
            return {"success": False, "error": "No entity IDs provided"}

        success_count = 0
        error_count = 0
        errors = []

        for entity_id in entity_ids:
            result = await self.db.execute(
                select(model).where(model.id == entity_id)
            )
            entity = result.scalar_one_or_none()
            if entity:
                await self.db.delete(entity)
                success_count += 1
            else:
                error_count += 1
                errors.append(f"{entity_type} with id {entity_id} not found")

        await self.db.flush()

        return {
            "success": True,
            "entity_type": entity_type,
            "success_count": success_count,
            "error_count": error_count,
            "errors": errors,
        }
