"""Admin dashboard API routes.

All endpoints require admin-level access (is_superuser or role=admin).
"""

from datetime import datetime, timedelta, timezone
from typing import List

from fastapi import APIRouter, HTTPException
from sqlalchemy import select, func, update
from sqlalchemy.orm import load_only

from src.core.constants import HTTPStatus
from src.core.router_utils import DBSession, CurrentUser, raise_forbidden, raise_not_found
from src.auth.models import User
from src.contacts.models import Contact
from src.companies.models import Company
from src.leads.models import Lead
from src.opportunities.models import Opportunity, PipelineStage
from src.quotes.models import Quote
from src.proposals.models import Proposal
from src.payments.models import Payment
from src.audit.models import AuditLog
from src.admin.schemas import (
    AdminUserResponse,
    AdminUserUpdate,
    AssignRoleRequest,
    SystemStats,
    TeamMemberOverview,
    ActivityFeedEntry,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _require_admin(user: User) -> None:
    """Raise 403 if the user is not an admin or superuser."""
    if user.is_superuser:
        return
    if getattr(user, "role", None) == "admin":
        return
    raise_forbidden("Admin access required")


# ---------------------------------------------------------------------------
# GET /api/admin/users
# ---------------------------------------------------------------------------
@router.get("/users", response_model=List[AdminUserResponse])
async def list_admin_users(
    current_user: CurrentUser,
    db: DBSession,
):
    """List all users with roles, status, last login and record counts."""
    _require_admin(current_user)

    users_result = await db.execute(select(User).order_by(User.id))
    users = users_result.scalars().all()

    # Aggregate counts per owner
    lead_counts = dict(
        (await db.execute(
            select(Lead.owner_id, func.count(Lead.id)).group_by(Lead.owner_id)
        )).all()
    )
    contact_counts = dict(
        (await db.execute(
            select(Contact.owner_id, func.count(Contact.id)).group_by(Contact.owner_id)
        )).all()
    )
    opp_counts = dict(
        (await db.execute(
            select(Opportunity.owner_id, func.count(Opportunity.id)).group_by(Opportunity.owner_id)
        )).all()
    )

    result = []
    for u in users:
        result.append(AdminUserResponse(
            id=u.id,
            email=u.email,
            full_name=u.full_name,
            role=u.role or "sales_rep",
            is_active=u.is_active,
            is_superuser=u.is_superuser,
            last_login=u.last_login,
            created_at=u.created_at if hasattr(u, "created_at") else None,
            lead_count=lead_counts.get(u.id, 0),
            contact_count=contact_counts.get(u.id, 0),
            opportunity_count=opp_counts.get(u.id, 0),
        ))
    return result


# ---------------------------------------------------------------------------
# PATCH /api/admin/users/{id}
# ---------------------------------------------------------------------------
@router.patch("/users/{user_id}", response_model=AdminUserResponse)
async def update_admin_user(
    user_id: int,
    data: AdminUserUpdate,
    current_user: CurrentUser,
    db: DBSession,
):
    """Update a user's role or active status."""
    _require_admin(current_user)

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise_not_found("User", user_id)

    if data.role is not None:
        user.role = data.role
    if data.is_active is not None:
        user.is_active = data.is_active

    await db.commit()
    await db.refresh(user)

    return AdminUserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role or "sales_rep",
        is_active=user.is_active,
        is_superuser=user.is_superuser,
        last_login=user.last_login,
        created_at=user.created_at if hasattr(user, "created_at") else None,
    )


# ---------------------------------------------------------------------------
# DELETE /api/admin/users/{id}  (soft-delete = deactivate)
# ---------------------------------------------------------------------------
@router.delete("/users/{user_id}")
async def deactivate_user(
    user_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Soft-delete (deactivate) a user."""
    _require_admin(current_user)

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise_not_found("User", user_id)

    user.is_active = False
    await db.commit()
    return {"detail": f"User {user_id} deactivated"}


# ---------------------------------------------------------------------------
# GET /api/admin/stats
# ---------------------------------------------------------------------------
@router.get("/stats", response_model=SystemStats)
async def get_system_stats(
    current_user: CurrentUser,
    db: DBSession,
):
    """System-wide stats: totals and active users in last 7 days."""
    _require_admin(current_user)

    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)

    total_users = (await db.execute(select(func.count(User.id)))).scalar() or 0
    total_contacts = (await db.execute(select(func.count(Contact.id)))).scalar() or 0
    total_companies = (await db.execute(select(func.count(Company.id)))).scalar() or 0
    total_leads = (await db.execute(select(func.count(Lead.id)))).scalar() or 0
    total_opps = (await db.execute(select(func.count(Opportunity.id)))).scalar() or 0
    total_quotes = (await db.execute(select(func.count(Quote.id)))).scalar() or 0
    total_proposals = (await db.execute(select(func.count(Proposal.id)))).scalar() or 0
    total_payments = (await db.execute(select(func.count(Payment.id)))).scalar() or 0
    active_users = (await db.execute(
        select(func.count(User.id)).where(
            User.last_login >= seven_days_ago,
            User.is_active == True,
        )
    )).scalar() or 0

    return SystemStats(
        total_users=total_users,
        total_contacts=total_contacts,
        total_companies=total_companies,
        total_leads=total_leads,
        total_opportunities=total_opps,
        total_quotes=total_quotes,
        total_proposals=total_proposals,
        total_payments=total_payments,
        active_users_7d=active_users,
    )


# ---------------------------------------------------------------------------
# GET /api/admin/team-overview
# ---------------------------------------------------------------------------
@router.get("/team-overview", response_model=List[TeamMemberOverview])
async def get_team_overview(
    current_user: CurrentUser,
    db: DBSession,
):
    """Per-user breakdown: leads, opportunities, pipeline value, won deals."""
    _require_admin(current_user)

    users_result = await db.execute(
        select(User).where(User.is_active == True).order_by(User.id)
    )
    users = users_result.scalars().all()

    lead_counts = dict(
        (await db.execute(
            select(Lead.owner_id, func.count(Lead.id)).group_by(Lead.owner_id)
        )).all()
    )
    opp_counts = dict(
        (await db.execute(
            select(Opportunity.owner_id, func.count(Opportunity.id)).group_by(Opportunity.owner_id)
        )).all()
    )

    # Pipeline value per user (open deals only)
    pipeline_result = await db.execute(
        select(
            Opportunity.owner_id,
            func.coalesce(func.sum(Opportunity.amount), 0),
        )
        .join(PipelineStage)
        .where(PipelineStage.is_won == False, PipelineStage.is_lost == False)
        .group_by(Opportunity.owner_id)
    )
    pipeline_values = dict(pipeline_result.all())

    # Won deals per user
    won_result = await db.execute(
        select(
            Opportunity.owner_id,
            func.count(Opportunity.id),
        )
        .join(PipelineStage)
        .where(PipelineStage.is_won == True)
        .group_by(Opportunity.owner_id)
    )
    won_counts = dict(won_result.all())

    overview = []
    for u in users:
        overview.append(TeamMemberOverview(
            user_id=u.id,
            user_name=u.full_name,
            role=u.role or "sales_rep",
            lead_count=lead_counts.get(u.id, 0),
            opportunity_count=opp_counts.get(u.id, 0),
            total_pipeline_value=float(pipeline_values.get(u.id, 0)),
            won_deals=won_counts.get(u.id, 0),
        ))
    return overview


# ---------------------------------------------------------------------------
# GET /api/admin/activity-feed
# ---------------------------------------------------------------------------
@router.get("/activity-feed", response_model=List[ActivityFeedEntry])
async def get_activity_feed(
    current_user: CurrentUser,
    db: DBSession,
    limit: int = 50,
):
    """Recent audit log entries across all users (last N entries)."""
    _require_admin(current_user)

    result = await db.execute(
        select(AuditLog)
        .order_by(AuditLog.timestamp.desc())
        .limit(limit)
    )
    logs = result.scalars().all()

    # Fetch user names for the feed
    user_ids = {log.user_id for log in logs if log.user_id}
    user_names = {}
    if user_ids:
        users_result = await db.execute(
            select(User.id, User.full_name).where(User.id.in_(user_ids))
        )
        user_names = dict(users_result.all())

    entries = []
    for log in logs:
        entries.append(ActivityFeedEntry(
            id=log.id,
            entity_type=log.entity_type,
            entity_id=log.entity_id,
            action=log.action,
            user_id=log.user_id,
            user_name=user_names.get(log.user_id) if log.user_id else None,
            timestamp=log.timestamp,
            changes=log.changes,
        ))
    return entries


# ---------------------------------------------------------------------------
# POST /api/admin/users/{id}/assign-role
# ---------------------------------------------------------------------------
@router.post("/users/{user_id}/assign-role", response_model=AdminUserResponse)
async def assign_role(
    user_id: int,
    data: AssignRoleRequest,
    current_user: CurrentUser,
    db: DBSession,
):
    """Assign a role to a user."""
    _require_admin(current_user)

    valid_roles = {"admin", "manager", "sales_rep", "viewer"}
    if data.role not in valid_roles:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=f"Invalid role. Must be one of: {', '.join(sorted(valid_roles))}",
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise_not_found("User", user_id)

    user.role = data.role
    await db.commit()
    await db.refresh(user)

    return AdminUserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role or "sales_rep",
        is_active=user.is_active,
        is_superuser=user.is_superuser,
        last_login=user.last_login,
        created_at=user.created_at if hasattr(user, "created_at") else None,
    )
