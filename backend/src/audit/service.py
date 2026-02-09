"""Audit log service layer."""

import json
from typing import Optional, List, Tuple
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from src.audit.models import AuditLog
from src.audit.schemas import AuditChangeDetail
from src.core.constants import DEFAULT_PAGE_SIZE


class AuditService:
    """Service for audit log operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_entity_log(
        self,
        entity_type: str,
        entity_id: int,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> Tuple[List[dict], int]:
        """Get paginated audit log for an entity."""
        base_filter = (
            AuditLog.entity_type == entity_type,
            AuditLog.entity_id == entity_id,
        )

        # Count
        count_query = select(func.count()).select_from(
            select(AuditLog.id).where(*base_filter).subquery()
        )
        total = (await self.db.execute(count_query)).scalar() or 0

        # Fetch
        offset = (page - 1) * page_size
        query = (
            select(AuditLog)
            .where(*base_filter)
            .order_by(AuditLog.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        result = await self.db.execute(query)
        rows = result.scalars().all()

        items = []
        for row in rows:
            changes = None
            if row.changes:
                try:
                    raw = json.loads(row.changes)
                    changes = [AuditChangeDetail(**c) for c in raw]
                except (json.JSONDecodeError, TypeError):
                    changes = None

            items.append(
                {
                    "id": row.id,
                    "entity_type": row.entity_type,
                    "entity_id": row.entity_id,
                    "action": row.action,
                    "changes": changes,
                    "user_id": row.user_id,
                    "user_name": row.user_name,
                    "user_email": row.user_email,
                    "created_at": row.created_at,
                }
            )

        return items, total

    async def log_action(
        self,
        entity_type: str,
        entity_id: int,
        action: str,
        changes: Optional[List[dict]] = None,
        user_id: Optional[int] = None,
        user_name: Optional[str] = None,
        user_email: Optional[str] = None,
    ) -> AuditLog:
        """Create an audit log entry."""
        changes_json = json.dumps(changes) if changes else None
        entry = AuditLog(
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            changes=changes_json,
            user_id=user_id,
            user_name=user_name,
            user_email=user_email,
        )
        self.db.add(entry)
        await self.db.flush()
        await self.db.refresh(entry)
        return entry
