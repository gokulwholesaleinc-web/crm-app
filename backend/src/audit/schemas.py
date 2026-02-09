"""Pydantic schemas for audit log."""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict


class AuditChangeDetail(BaseModel):
    """A single field change within an audit log entry."""

    field: str
    old_value: Optional[str] = None
    new_value: Optional[str] = None


class AuditLogResponse(BaseModel):
    """Response schema for a single audit log entry."""

    id: int
    entity_type: str
    entity_id: int
    action: str
    changes: Optional[List[AuditChangeDetail]] = None
    user_id: Optional[int] = None
    user_name: Optional[str] = None
    user_email: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AuditLogListResponse(BaseModel):
    """Paginated list of audit log entries."""

    items: List[AuditLogResponse]
    total: int
    page: int
    page_size: int
    pages: int
