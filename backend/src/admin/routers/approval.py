"""Admin approval workflow endpoints: pending users, approve, reject, rejected emails."""

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from src.admin._router_helpers import _require_admin
from src.admin.schemas import (
    ApproveUserRequest,
    PendingUserResponse,
    RejectedEmailResponse,
    RejectUserRequest,
)
from src.auth.dependencies import invalidate_user_cache
from src.auth.models import RejectedAccessEmail, User
from src.core.constants import HTTPStatus
from src.core.rate_limit import limiter
from src.core.router_utils import CurrentUser, DBSession, raise_not_found

router = APIRouter()


@router.get("/users/pending", response_model=list[PendingUserResponse])
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


@router.get("/rejected-emails", response_model=list[RejectedEmailResponse])
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
