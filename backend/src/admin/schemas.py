"""Admin dashboard Pydantic schemas."""

from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, EmailStr

from src.roles.models import RoleName


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
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None


class AssignRoleRequest(BaseModel):
    """Request body to assign a role to a user."""
    role: str


class LinkTenantRequest(BaseModel):
    """Request body to link a user to a tenant."""
    tenant_slug: str = "default"
    role: str = "member"
    is_primary: bool = True


class LinkTenantResponse(BaseModel):
    """Response after linking a user to a tenant."""
    user_id: int
    tenant_id: int
    tenant_slug: str
    role: str
    is_primary: bool


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
    changes: Optional[Any] = None

    model_config = {"from_attributes": True}




# ---------------------------------------------------------------------------
# User approval schemas
# ---------------------------------------------------------------------------

class PendingUserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    avatar_url: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ApproveUserRequest(BaseModel):
    role: RoleName = RoleName.SALES_REP


class RejectUserRequest(BaseModel):
    reason: Optional[str] = None


class RejectedEmailResponse(BaseModel):
    id: int
    email: str
    rejected_by_id: Optional[int] = None
    rejected_by_email: Optional[str] = None
    rejected_at: datetime
    reason: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}
