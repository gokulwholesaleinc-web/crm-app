"""Audit log service for recording and retrieving entity changes."""

from typing import Optional, List, Tuple, Any
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from src.audit.models import AuditLog
from src.auth.models import User
from src.core.constants import DEFAULT_PAGE_SIZE


class AuditService:
    """Service for audit log operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def log_change(
        self,
        entity_type: str,
        entity_id: int,
        user_id: Optional[int],
        action: str,
        changes: Optional[List[dict]] = None,
        ip_address: Optional[str] = None,
    ) -> AuditLog:
        """Record an audit log entry."""
        entry = AuditLog(
            entity_type=entity_type,
            entity_id=entity_id,
            user_id=user_id,
            action=action,
            changes=changes,
            ip_address=ip_address,
        )
        self.db.add(entry)
        await self.db.flush()
        await self.db.refresh(entry)
        return entry

    async def get_entity_history(
        self,
        entity_type: str,
        entity_id: int,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> Tuple[List[dict], int]:
        """Get paginated audit history for a specific entity."""
        base_filter = [
            AuditLog.entity_type == entity_type,
            AuditLog.entity_id == entity_id,
        ]

        # Count
        count_query = select(func.count()).select_from(
            select(AuditLog.id).where(*base_filter).subquery()
        )
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Fetch with user name join
        query = (
            select(AuditLog, User.full_name.label("user_name"))
            .outerjoin(User, AuditLog.user_id == User.id)
            .where(*base_filter)
            .order_by(AuditLog.timestamp.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self.db.execute(query)
        rows = result.all()

        items = []
        for log, user_name in rows:
            items.append({
                "id": log.id,
                "entity_type": log.entity_type,
                "entity_id": log.entity_id,
                "user_id": log.user_id,
                "user_name": user_name,
                "action": log.action,
                "changes": log.changes,
                "ip_address": log.ip_address,
                "timestamp": log.timestamp,
            })

        return items, total


def detect_changes(old_data: dict, new_data: dict) -> List[dict]:
    """Compare old and new data dicts and return list of changed fields.

    Args:
        old_data: Dictionary of old field values
        new_data: Dictionary of new field values (only fields being updated)

    Returns:
        List of dicts with field, old_value, new_value for each changed field
    """
    changes = []
    for field, new_value in new_data.items():
        old_value = old_data.get(field)
        # Convert to comparable strings for comparison
        old_str = _to_comparable(old_value)
        new_str = _to_comparable(new_value)
        if old_str != new_str:
            changes.append({
                "field": field,
                "old_value": _serialize(old_value),
                "new_value": _serialize(new_value),
            })
    return changes


def _to_comparable(value: Any) -> str:
    """Convert a value to a comparable string representation."""
    if value is None:
        return ""
    return str(value)


def _serialize(value: Any) -> Any:
    """Serialize a value for JSON storage."""
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value) if not isinstance(value, (str, int, float, bool)) else value
