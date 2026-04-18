"""Admin user CRUD, role assignment, and tenant linking endpoints."""

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import func, select

from src.admin._router_helpers import _require_admin
from src.admin.schemas import (
    AdminUserResponse,
    AdminUserUpdate,
    AssignRoleRequest,
    LinkTenantRequest,
    LinkTenantResponse,
)
from src.auth.dependencies import invalidate_user_cache
from src.auth.models import User
from src.contacts.models import Contact
from src.core.constants import HTTPStatus
from src.core.rate_limit import limiter
from src.core.router_utils import CurrentUser, DBSession, raise_not_found
from src.leads.models import Lead
from src.opportunities.models import Opportunity
from src.whitelabel.models import Tenant, TenantUser

router = APIRouter()


# ---------------------------------------------------------------------------
# GET /api/admin/users
# ---------------------------------------------------------------------------
@router.get("/users", response_model=list[AdminUserResponse])
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
