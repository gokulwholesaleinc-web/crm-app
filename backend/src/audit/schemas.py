"""Pydantic schemas for audit log."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AuditChangeDetail(BaseModel):
    """A single field change within an audit log entry."""

    field: str
    old_value: str | None = None
    new_value: str | None = None


class AuditLogResponse(BaseModel):
    """Response schema for a single audit log entry."""

    id: int
    entity_type: str
    entity_id: int
    action: str
    changes: list[AuditChangeDetail] | None = None
    user_id: int | None = None
    user_name: str | None = None
    user_email: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AuditLogListResponse(BaseModel):
    """Paginated list of audit log entries."""

    items: list[AuditLogResponse]
    total: int
    page: int
    page_size: int
    pages: int
