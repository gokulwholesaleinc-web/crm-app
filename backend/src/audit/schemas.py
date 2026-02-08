"""Pydantic schemas for audit logs."""

from datetime import datetime
from typing import Optional, List, Any
from pydantic import BaseModel, ConfigDict


class AuditChangeDetail(BaseModel):
    field: str
    old_value: Any = None
    new_value: Any = None


class AuditLogResponse(BaseModel):
    id: int
    entity_type: str
    entity_id: int
    user_id: Optional[int] = None
    user_name: Optional[str] = None
    action: str
    changes: Optional[List[AuditChangeDetail]] = None
    ip_address: Optional[str] = None
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)


class AuditLogListResponse(BaseModel):
    items: List[AuditLogResponse]
    total: int
    page: int
    page_size: int
    pages: int
