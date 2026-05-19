"""Pydantic schemas for audit log."""

from datetime import datetime
from typing import Any

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


class WorkSessionHeartbeatRequest(BaseModel):
    """Heartbeat payload sent from visible, recently-active CRM detail pages."""

    entity_type: str
    entity_id: int
    source: str = "detail_page"
    metadata: dict[str, Any] | None = None


class WorkSessionResponse(BaseModel):
    """Estimated active CRM work session."""

    id: int
    user_id: int | None = None
    user_name: str | None = None
    entity_type: str
    entity_id: int
    started_at: datetime
    last_seen_at: datetime
    ended_at: datetime | None = None
    duration_seconds: int
    source: str
    metadata: dict[str, Any] | None = None


class AdminAuditFeedItem(BaseModel):
    """Audit feed row enriched for the admin dashboard."""

    id: int
    entity_type: str
    entity_id: int
    action: str
    changes: Any | None = None
    user_id: int | None = None
    user_name: str | None = None
    user_email: str | None = None
    ip_address: str | None = None
    created_at: datetime


class AdminAuditFeedResponse(BaseModel):
    """Paginated admin audit feed."""

    items: list[AdminAuditFeedItem]
    total: int
    page: int
    page_size: int
    pages: int


class AdminAuditTotals(BaseModel):
    """Top-line dashboard totals."""

    audit_events: int = 0
    active_crm_seconds: int = 0
    activities: int = 0
    calls: int = 0
    emails: int = 0
    security_events: int = 0


class AdminAuditUserSummary(BaseModel):
    """Per-user active CRM time and touch metrics."""

    user_id: int
    user_name: str
    user_email: str | None = None
    role: str | None = None
    active_crm_seconds: int = 0
    audit_events: int = 0
    calls: int = 0
    call_duration_minutes: int = 0
    emails: int = 0
    proposals_touched: int = 0
    opportunities_touched: int = 0
    last_active_at: datetime | None = None


class AdminAuditEntitySummary(BaseModel):
    """Per-entity activity/time rollup."""

    entity_type: str
    entity_id: int
    label: str | None = None
    owner_id: int | None = None
    owner_name: str | None = None
    active_crm_seconds: int = 0
    activity_count: int = 0
    audit_count: int = 0
    last_touched_at: datetime | None = None
    last_touched_by_id: int | None = None
    last_touched_by_name: str | None = None


class AdminAuditSecurityEvent(BaseModel):
    """Security-relevant audit signal for the dashboard."""

    id: str
    severity: str
    category: str
    description: str
    user_id: int | None = None
    user_name: str | None = None
    entity_type: str | None = None
    entity_id: int | None = None
    count: int = 1
    created_at: datetime


class AdminAuditSummaryResponse(BaseModel):
    """Admin audit dashboard summary."""

    start_at: datetime | None = None
    end_at: datetime | None = None
    totals: AdminAuditTotals
    users: list[AdminAuditUserSummary]
    entities: list[AdminAuditEntitySummary]
    security: list[AdminAuditSecurityEvent]


class AdminAuditUserDetail(BaseModel):
    """Detailed audit/time view for one user."""

    summary: AdminAuditUserSummary
    feed: AdminAuditFeedResponse
    sessions: list[WorkSessionResponse]


class AdminAuditEntityDetail(BaseModel):
    """Detailed audit/time view for one entity."""

    summary: AdminAuditEntitySummary
    feed: AdminAuditFeedResponse
    sessions: list[WorkSessionResponse]
