"""Authentication API routes."""

import hmac as _hmac
import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import select

from src.auth import google_oauth
from src.auth.schemas import (
    GoogleAuthorizeRequest,
    GoogleAuthorizeResponse,
    GoogleCallbackRequest,
    TenantInfo,
    Token,
    UserResponse,
    UserUpdate,
)
from src.auth.security import create_access_token
from src.auth.service import AuthService, RejectedAccessError
from src.config import settings
from src.core.constants import HTTPStatus
from src.core.rate_limit import limiter
from src.core.router_utils import CurrentUser, DBSession
from src.notifications.service import notify_admins_of_pending_user
from src.whitelabel.models import Tenant, TenantSettings, TenantUser

router = APIRouter(prefix="/api/auth", tags=["auth"])


async def _get_user_tenant_info(db, user_id: int) -> list | None:
    """Fetch tenant memberships for a user and return as TenantInfo dicts."""
    result = await db.execute(
        select(TenantUser, Tenant, TenantSettings)
        .join(Tenant, TenantUser.tenant_id == Tenant.id)
        .outerjoin(TenantSettings, TenantSettings.tenant_id == Tenant.id)
        .where(TenantUser.user_id == user_id)
    )
    rows = result.all()
    if not rows:
        return None
    tenants = []
    for tu, tenant, tenant_settings in rows:
        tenants.append(
            TenantInfo(
                tenant_id=tenant.id,
                tenant_slug=tenant.slug,
                company_name=tenant_settings.company_name if tenant_settings else tenant.name,
                role=tu.role,
                is_primary=tu.is_primary,
                primary_color=tenant_settings.primary_color if tenant_settings else None,
                secondary_color=tenant_settings.secondary_color if tenant_settings else None,
                accent_color=tenant_settings.accent_color if tenant_settings else None,
                logo_url=tenant_settings.logo_url if tenant_settings else None,
            ).model_dump()
        )
    return tenants


# Google OAuth2 sign-in

GOOGLE_OAUTH_STATE_COOKIE = "crm_google_oauth_state"
GOOGLE_OAUTH_STATE_TTL_SECONDS = 600  # 10 minutes: plenty for a consent screen


def get_google_http_factory() -> google_oauth.HttpClientFactory:
    """Default httpx.AsyncClient factory used by Google sign-in endpoints."""
    return google_oauth.default_client_factory


GoogleHttpFactory = Annotated[
    google_oauth.HttpClientFactory, Depends(get_google_http_factory)
]


@router.post("/google/authorize", response_model=GoogleAuthorizeResponse)
@limiter.limit("15/minute")
async def google_authorize(
    request: Request,
    response: Response,
    data: GoogleAuthorizeRequest,
):
    """Return the Google consent URL to start sign-in."""
    client_id = settings.GOOGLE_CLIENT_ID
    if not client_id:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="Google sign-in is not configured",
        )
    state = secrets.token_urlsafe(24)
    auth_url = google_oauth.build_authorize_url(
        client_id=client_id,
        redirect_uri=data.redirect_uri,
        state=state,
    )

    # HttpOnly so XSS can't read it. In prod the frontend and backend run
    # on different Railway subdomains (both under the `up.railway.app`
    # public suffix), so the callback XHR is cross-site — SameSite=Lax
    # would drop the cookie and the callback would 400. SameSite=None
    # requires Secure, which is already enforced outside debug builds.
    # In debug we stay on Lax because local dev is same-site and None
    # without Secure would be rejected.
    cross_site = not settings.DEBUG
    response.set_cookie(
        key=GOOGLE_OAUTH_STATE_COOKIE,
        value=state,
        max_age=GOOGLE_OAUTH_STATE_TTL_SECONDS,
        httponly=True,
        secure=cross_site,
        samesite="none" if cross_site else "lax",
        path="/",
    )
    return GoogleAuthorizeResponse(auth_url=auth_url, state=state)


@router.post("/google/callback", response_model=Token)
@limiter.limit("15/minute")
async def google_callback(
    request: Request,
    response: Response,
    data: GoogleCallbackRequest,
    db: DBSession,
    http_factory: GoogleHttpFactory,
):
    """Exchange Google's code for a CRM session."""
    client_id = settings.GOOGLE_CLIENT_ID
    client_secret = settings.GOOGLE_CLIENT_SECRET
    if not client_id or not client_secret:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="Google sign-in is not configured",
        )

    cookie_state = request.cookies.get(GOOGLE_OAUTH_STATE_COOKIE) or ""
    body_state = data.state or ""
    if not cookie_state or not body_state or not _hmac.compare_digest(cookie_state, body_state):
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="OAuth state mismatch. Please start sign-in again from the login page.",
        )
    response.delete_cookie(GOOGLE_OAUTH_STATE_COOKIE, path="/")

    try:
        token_data = await google_oauth.exchange_code_for_tokens(
            code=data.code,
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=data.redirect_uri,
            client_factory=http_factory,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=f"Google token exchange failed: {str(exc)}",
        ) from exc

    access_token = token_data.get("access_token")
    if not access_token:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="Google did not return an access_token",
        )

    try:
        profile = await google_oauth.fetch_userinfo(
            access_token=access_token,
            client_factory=http_factory,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=f"Failed to fetch Google profile: {str(exc)}",
        ) from exc

    google_sub = profile.get("sub")
    email = profile.get("email")
    if not google_sub or not email:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="Google profile missing sub or email",
        )
    if profile.get("email_verified") is False:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="Google account email is not verified",
        )

    service = AuthService(db)

    try:
        user = await service.upsert_google_user(
            google_sub=str(google_sub),
            email=email,
            full_name=profile.get("name") or email.split("@")[0],
            avatar_url=profile.get("picture"),
        )
    except RejectedAccessError as exc:
        raise HTTPException(
            status_code=403,
            detail={"rejected": True, "detail": "Access denied. Contact an admin if this is a mistake."},
        ) from exc

    if not user.is_approved:
        # Notify admins on first pending sign-in (no tenant yet means brand new)
        existing_membership = await db.execute(
            select(TenantUser).where(TenantUser.user_id == user.id)
        )
        if existing_membership.scalar_one_or_none() is None:
            await notify_admins_of_pending_user(db, user)
            # Attach to tenant so repeat sign-ins don't re-notify
            tenant_slug = getattr(request.state, "tenant_slug_hint", None) or "default"
            result = await db.execute(select(Tenant).where(Tenant.slug == tenant_slug))
            tenant = result.scalar_one_or_none()
            if tenant:
                db.add(TenantUser(
                    user_id=user.id,
                    tenant_id=tenant.id,
                    role="member",
                    is_primary=True,
                ))

        await db.commit()
        raise HTTPException(
            status_code=403,
            detail={"pending_approval": True, "detail": "Your account is pending admin approval. You'll receive a notification when approved."},
        )

    # Attach to default tenant if the user is brand new (no tenant memberships).
    existing_membership = await db.execute(
        select(TenantUser).where(TenantUser.user_id == user.id)
    )
    if existing_membership.scalar_one_or_none() is None:
        tenant_slug = getattr(request.state, "tenant_slug_hint", None) or "default"
        result = await db.execute(select(Tenant).where(Tenant.slug == tenant_slug))
        tenant = result.scalar_one_or_none()
        if tenant:
            db.add(TenantUser(
                user_id=user.id,
                tenant_id=tenant.id,
                role="member",
                is_primary=True,
            ))

    await db.commit()
    await db.refresh(user)

    jwt_token = create_access_token(data={"sub": str(user.id)})
    tenants = await _get_user_tenant_info(db, user.id)
    return Token(access_token=jwt_token, tenants=tenants)


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: CurrentUser,
):
    """Get current user profile."""
    return current_user


@router.get("/me/tenants", response_model=list[TenantInfo])
async def get_my_tenants(
    current_user: CurrentUser,
    db: DBSession,
):
    """Get tenant memberships for the current user."""
    tenants = await _get_user_tenant_info(db, current_user.id)
    return tenants or []


@router.patch("/me", response_model=UserResponse)
async def update_me(
    user_data: UserUpdate,
    current_user: CurrentUser,
    db: DBSession,
):
    """Update current user profile."""
    service = AuthService(db)
    updated_user = await service.update_user(current_user, user_data)
    return updated_user


@router.get("/users", response_model=list[UserResponse])
async def list_users(
    current_user: CurrentUser,
    db: DBSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=200),
):
    """List all users (for assignment dropdowns, etc.)."""
    service = AuthService(db)
    users = await service.get_all_users(page=page, page_size=page_size)
    return users
