"""Utility functions for integrating audit logging with entity operations."""

from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from src.audit.service import AuditService, detect_changes


async def audit_entity_create(
    db: AsyncSession,
    entity_type: str,
    entity_id: int,
    user_id: Optional[int],
    ip_address: Optional[str] = None,
) -> None:
    """Log an entity creation."""
    service = AuditService(db)
    await service.log_change(
        entity_type=entity_type,
        entity_id=entity_id,
        user_id=user_id,
        action="create",
        ip_address=ip_address,
    )


async def audit_entity_update(
    db: AsyncSession,
    entity_type: str,
    entity_id: int,
    user_id: Optional[int],
    old_data: dict,
    new_data: dict,
    ip_address: Optional[str] = None,
) -> None:
    """Log an entity update with field-level change tracking."""
    changes = detect_changes(old_data, new_data)
    if not changes:
        return  # No actual changes, skip logging

    service = AuditService(db)
    await service.log_change(
        entity_type=entity_type,
        entity_id=entity_id,
        user_id=user_id,
        action="update",
        changes=changes,
        ip_address=ip_address,
    )


async def audit_entity_delete(
    db: AsyncSession,
    entity_type: str,
    entity_id: int,
    user_id: Optional[int],
    ip_address: Optional[str] = None,
) -> None:
    """Log an entity deletion."""
    service = AuditService(db)
    await service.log_change(
        entity_type=entity_type,
        entity_id=entity_id,
        user_id=user_id,
        action="delete",
        ip_address=ip_address,
    )


def snapshot_entity(entity, fields: list[str]) -> dict:
    """Take a snapshot of entity fields for comparison before update.

    Args:
        entity: SQLAlchemy model instance
        fields: List of field names to snapshot

    Returns:
        Dictionary of field name -> current value
    """
    data = {}
    for field in fields:
        value = getattr(entity, field, None)
        data[field] = value
    return data
