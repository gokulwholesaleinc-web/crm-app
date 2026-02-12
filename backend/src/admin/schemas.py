"""Admin dashboard Pydantic schemas."""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


class AdminUserResponse(BaseModel):
    """User record with role, status, and record counts."""
    id: int
    email: str
    full_name: str
    role: str
    is_active: bool
    is_superuser: bool
    last_login: Optional[datetime] = None
    created_at: Optional[datetime] = None
    lead_count: int = 0
    contact_count: int = 0
    opportunity_count: int = 0

    model_config = {"from_attributes": True}


class AdminUserUpdate(BaseModel):
    """Fields an admin can update on a user."""
    role: Optional[str] = None
    is_active: Optional[bool] = None


class AssignRoleRequest(BaseModel):
    """Request body to assign a role to a user."""
    role: str


class SystemStats(BaseModel):
    """System-wide aggregate statistics."""
    total_users: int = 0
    total_contacts: int = 0
    total_companies: int = 0
    total_leads: int = 0
    total_opportunities: int = 0
    total_quotes: int = 0
    total_proposals: int = 0
    total_payments: int = 0
    active_users_7d: int = 0


class TeamMemberOverview(BaseModel):
    """Per-user breakdown for the team overview."""
    user_id: int
    user_name: str
    role: str
    lead_count: int = 0
    opportunity_count: int = 0
    total_pipeline_value: float = 0.0
    won_deals: int = 0


class ActivityFeedEntry(BaseModel):
    """A single entry from the audit log activity feed."""
    id: int
    entity_type: str
    entity_id: int
    action: str
    user_id: Optional[int] = None
    user_name: Optional[str] = None
    timestamp: datetime
    changes: Optional[dict] = None

    model_config = {"from_attributes": True}


class CacheStatsResponse(BaseModel):
    """Cache statistics."""
    total_keys: int = 0
    active_keys: int = 0
    expired_keys: int = 0
    memory_bytes: int = 0
    hits: int = 0
    misses: int = 0
    hit_rate_percent: float = 0.0


class CacheClearResponse(BaseModel):
    """Response for cache clear operations."""
    cleared_count: int = 0
    message: str = ""
