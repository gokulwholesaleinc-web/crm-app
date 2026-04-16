"""Admin dashboard API routes.

All endpoints require admin-level access (is_superuser or role=admin).
"""

from datetime import datetime, timedelta, timezone
from typing import List

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import select, func

from src.core.constants import HTTPStatus
from src.core.rate_limit import limiter
from src.core.router_utils import DBSession, CurrentUser, raise_forbidden, raise_not_found
from src.auth.dependencies import invalidate_user_cache
from src.auth.models import User, RejectedAccessEmail
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
    ApproveUserRequest,
    AssignRoleRequest,
    LinkTenantRequest,
    LinkTenantResponse,
    PendingUserResponse,
    RejectUserRequest,
    RejectedEmailResponse,
    SystemStats,
    TeamMemberOverview,
    ActivityFeedEntry,
)
from src.whitelabel.models import Tenant, TenantUser

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
@limiter.limit("30/minute")
async def list_admin_users(
    request: Request,
    current_user: CurrentUser,
    db: DBSession,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
):
    """List users with roles, status, last login and record counts."""
    _require_admin(current_user)

    users_result = await db.execute(
        select(User).order_by(User.id).offset(skip).limit(limit)
    )
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
@limiter.limit("10/minute")
async def update_admin_user(
    request: Request,
    user_id: int,
    data: AdminUserUpdate,
    current_user: CurrentUser,
    db: DBSession,
):
    """Update a user's role, active status, email, or full name."""
    _require_admin(current_user)

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise_not_found("User", user_id)

    if data.role is not None:
        user.role = data.role
    if data.is_active is not None:
        user.is_active = data.is_active
    if data.email is not None:
        # Check email uniqueness
        existing = await db.execute(
            select(User.id).where(User.email == data.email, User.id != user_id)
        )
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=HTTPStatus.CONFLICT,
                detail="Email already in use by another user",
            )
        user.email = data.email
    if data.full_name is not None:
        user.full_name = data.full_name

    await db.commit()
    await db.refresh(user)
    invalidate_user_cache(user.id)

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
@limiter.limit("10/minute")
async def deactivate_user(
    request: Request,
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
    invalidate_user_cache(user_id)
    return {"detail": f"User {user_id} deactivated"}


# ---------------------------------------------------------------------------
# DELETE /api/admin/users/{id}/permanent
# ---------------------------------------------------------------------------
@router.delete("/users/{user_id}/permanent")
@limiter.limit("5/minute")
async def permanently_delete_user(
    request: Request,
    user_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Permanently delete a user and all their CASCADE-linked data.

    Related records with SET NULL foreign keys (contacts, leads, etc.)
    will have their owner_id/created_by_id set to NULL by the database.
    """
    _require_admin(current_user)

    if user_id == current_user.id:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="Cannot delete your own account",
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise_not_found("User", user_id)

    if user.is_superuser:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="Cannot delete a superuser account",
        )

    await db.delete(user)
    await db.commit()
    invalidate_user_cache(user_id)
    return {"detail": f"User {user_id} permanently deleted"}


# ---------------------------------------------------------------------------
# GET /api/admin/stats
# ---------------------------------------------------------------------------
@router.get("/stats", response_model=SystemStats)
@limiter.limit("30/minute")
async def get_system_stats(
    request: Request,
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
@limiter.limit("30/minute")
async def get_team_overview(
    request: Request,
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
@limiter.limit("30/minute")
async def get_activity_feed(
    request: Request,
    current_user: CurrentUser,
    db: DBSession,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
):
    """Recent audit log entries across all users with pagination."""
    _require_admin(current_user)

    result = await db.execute(
        select(AuditLog)
        .order_by(AuditLog.timestamp.desc())
        .offset(skip)
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
@limiter.limit("10/minute")
async def assign_role(
    request: Request,
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
    invalidate_user_cache(user.id)

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
# POST /api/admin/users/{id}/link-tenant
# ---------------------------------------------------------------------------
@router.post("/users/{user_id}/link-tenant", response_model=LinkTenantResponse)
@limiter.limit("10/minute")
async def link_user_to_tenant(
    request: Request,
    user_id: int,
    data: LinkTenantRequest,
    current_user: CurrentUser,
    db: DBSession,
):
    """Link a user to a tenant. Creates a TenantUser record."""
    _require_admin(current_user)

    # Verify user exists
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise_not_found("User", user_id)

    # Verify tenant exists
    result = await db.execute(select(Tenant).where(Tenant.slug == data.tenant_slug))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail=f"Tenant with slug '{data.tenant_slug}' not found",
        )

    # Check if link already exists
    result = await db.execute(
        select(TenantUser).where(
            TenantUser.user_id == user_id,
            TenantUser.tenant_id == tenant.id,
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=HTTPStatus.CONFLICT,
            detail="User is already linked to this tenant",
        )

    tenant_user = TenantUser(
        user_id=user_id,
        tenant_id=tenant.id,
        role=data.role,
        is_primary=data.is_primary,
    )
    db.add(tenant_user)
    await db.commit()

    return LinkTenantResponse(
        user_id=user_id,
        tenant_id=tenant.id,
        tenant_slug=tenant.slug,
        role=data.role,
        is_primary=data.is_primary,
    )


# ---------------------------------------------------------------------------
# Approval endpoints
# ---------------------------------------------------------------------------


@router.get("/users/pending", response_model=List[PendingUserResponse])
@limiter.limit("30/minute")
async def list_pending_users(
    request: Request,
    current_user: CurrentUser,
    db: DBSession,
):
    """List users awaiting admin approval."""
    _require_admin(current_user)
    result = await db.execute(
        select(User).where(User.is_approved == False).order_by(User.created_at.desc())
    )
    return result.scalars().all()


@router.patch("/users/{user_id}/approve", status_code=204)
@limiter.limit("10/minute")
async def approve_user(
    request: Request,
    user_id: int,
    data: ApproveUserRequest,
    current_user: CurrentUser,
    db: DBSession,
):
    """Approve a pending user and assign their role."""
    _require_admin(current_user)

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise_not_found("User", user_id)

    if user.is_approved:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="User is already approved",
        )

    user.is_approved = True
    user.role = data.role.value
    await db.commit()
    invalidate_user_cache(user.id)


@router.post("/users/{user_id}/reject")
@limiter.limit("10/minute")
async def reject_user(
    request: Request,
    user_id: int,
    data: RejectUserRequest,
    current_user: CurrentUser,
    db: DBSession,
):
    """Reject and delete a pending user, adding their email to the block list."""
    _require_admin(current_user)

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise_not_found("User", user_id)

    rejected = RejectedAccessEmail(
        email=user.email.lower(),
        rejected_by_id=current_user.id,
        reason=data.reason,
    )
    db.add(rejected)
    await db.flush()
    await db.delete(user)
    await db.commit()
    await db.refresh(rejected)
    invalidate_user_cache(user_id)
    return {"rejected_email_id": rejected.id}


@router.get("/rejected-emails", response_model=List[RejectedEmailResponse])
@limiter.limit("30/minute")
async def list_rejected_emails(
    request: Request,
    current_user: CurrentUser,
    db: DBSession,
):
    """List all rejected email addresses with the admin's email who rejected them."""
    _require_admin(current_user)
    result = await db.execute(
        select(RejectedAccessEmail, User.email)
        .outerjoin(User, User.id == RejectedAccessEmail.rejected_by_id)
        .order_by(RejectedAccessEmail.rejected_at.desc())
    )
    return [
        RejectedEmailResponse(
            id=r.id,
            email=r.email,
            rejected_by_id=r.rejected_by_id,
            rejected_by_email=by_email,
            rejected_at=r.rejected_at,
            reason=r.reason,
            created_at=r.created_at,
        )
        for r, by_email in result.all()
    ]


@router.delete("/rejected-emails/{rejected_id}", status_code=204)
@limiter.limit("10/minute")
async def delete_rejected_email(
    request: Request,
    rejected_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Remove an email from the reject list so the person can retry sign-in."""
    _require_admin(current_user)
    result = await db.execute(
        select(RejectedAccessEmail).where(RejectedAccessEmail.id == rejected_id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise_not_found("RejectedEmail", rejected_id)
    await db.delete(entry)
    await db.commit()
