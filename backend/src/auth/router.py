"""Authentication API routes."""

import hmac as _hmac
import secrets
from typing import Annotated, List
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from src.config import settings
from src.core.constants import HTTPStatus, ErrorMessages, EntityNames
from src.core.router_utils import DBSession, CurrentUser, raise_bad_request
from src.auth.models import User
from src.auth.schemas import (
    UserCreate,
    UserUpdate,
    UserResponse,
    Token,
    LoginRequest,
    TenantInfo,
    GoogleAuthorizeRequest,
    GoogleAuthorizeResponse,
    GoogleCallbackRequest,
)
from src.auth.service import AuthService
from src.auth.security import create_access_token
from src.auth.dependencies import get_current_active_user, get_current_superuser
from src.auth import google_oauth
from src.whitelabel.models import TenantUser, Tenant, TenantSettings

from src.core.rate_limit import limiter

router = APIRouter(prefix="/api/auth", tags=["auth"])


async def _get_user_tenant_info(db, user_id: int) -> list | None:
    """Fetch tenant memberships for a user and return as TenantInfo dicts.

    Uses a join query since TenantUser does not have a relationship to Tenant.
    """
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
    for tu, tenant, settings in rows:
        tenants.append(
            TenantInfo(
                tenant_id=tenant.id,
                tenant_slug=tenant.slug,
                company_name=settings.company_name if settings else tenant.name,
                role=tu.role,
                is_primary=tu.is_primary,
                primary_color=settings.primary_color if settings else None,
                secondary_color=settings.secondary_color if settings else None,
                accent_color=settings.accent_color if settings else None,
                logo_url=settings.logo_url if settings else None,
            ).model_dump()
        )
    return tenants


@router.post("/register", response_model=UserResponse, status_code=HTTPStatus.CREATED)
@limiter.limit("3/minute")
async def register(
    request: Request,
    user_data: UserCreate,
    db: DBSession,
):
    """Register a new user and auto-link to the default tenant."""
    service = AuthService(db)

    # Check if user already exists
    existing_user = await service.get_user_by_email(user_data.email)
    if existing_user:
        raise_bad_request("Email already registered")

    user = await service.create_user(user_data)

    tenant_slug = getattr(request.state, "tenant_slug_hint", None) or "default"
    result = await db.execute(
        select(Tenant).where(Tenant.slug == tenant_slug)
    )
    tenant = result.scalar_one_or_none()
    if tenant:
        tenant_user = TenantUser(
            user_id=user.id,
            tenant_id=tenant.id,
            role="member",
            is_primary=True,
        )
        db.add(tenant_user)
        await db.commit()
        await db.refresh(user)

    return user


@router.post("/login", response_model=Token)
@limiter.limit("15/minute")
async def login(
    request: Request,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: DBSession,
):
    """Login and get access token."""
    service = AuthService(db)
    user = await service.authenticate_user(form_data.username, form_data.password)

    if not user:
        raise HTTPException(
            status_code=HTTPStatus.UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(data={"sub": str(user.id)})
    tenants = await _get_user_tenant_info(db, user.id)
    return Token(access_token=access_token, tenants=tenants)


@router.post("/login/json", response_model=Token)
@limiter.limit("15/minute")
async def login_json(
    request: Request,
    login_data: LoginRequest,
    db: DBSession,
):
    """Login with JSON body and get access token."""
    service = AuthService(db)
    user = await service.authenticate_user(login_data.email, login_data.password)

    if not user:
        raise HTTPException(
            status_code=HTTPStatus.UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    access_token = create_access_token(data={"sub": str(user.id)})
    tenants = await _get_user_tenant_info(db, user.id)
    return Token(access_token=access_token, tenants=tenants)


# =============================================================================
# Google OAuth2 sign-in
# =============================================================================
#
# This flow is independent from /api/integrations/google-calendar:
# - Only requests openid/email/profile scopes (no calendar access)
# - Does NOT require the user to already be logged in (public endpoints)
# - Creates a user on first sign-in, or links google_sub to an existing
#   email-matched account.
#
# CSRF defense: the state nonce is minted by /authorize and stored in an
# HttpOnly, short-TTL cookie on the client's browser. The /callback
# endpoint reads that cookie and requires an `hmac.compare_digest` match
# with the `state` query string Google echoed back. A victim tricked
# into landing on the callback URL directly has no matching cookie in
# their browser, so the exchange is rejected.
#
# The HTTP factory used to talk to Google is overridable via
# `app.dependency_overrides[get_google_http_factory]` so tests can stub
# the token + userinfo endpoints without a live network.

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
    """Return the Google consent URL to start sign-in.

    Also sets an HttpOnly cookie containing the state nonce so the
    callback handler can verify it server-side. The response body still
    carries `state` for backwards compat with the previous frontend
    (which wrote it to sessionStorage); new clients can ignore it.
    """
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
    """Exchange Google's code for a CRM session.

    Creates or links a user from the verified Google profile and returns a
    CRM JWT + tenant list, mirroring `/login/json` so the frontend can reuse
    the same post-login flow.

    CSRF: requires the state query (echoed by Google) to match the
    HttpOnly cookie set by /authorize. Missing cookie = reject.
    """
    client_id = settings.GOOGLE_CLIENT_ID
    client_secret = settings.GOOGLE_CLIENT_SECRET
    if not client_id or not client_secret:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="Google sign-in is not configured",
        )

    # Server-side CSRF state verification.
    cookie_state = request.cookies.get(GOOGLE_OAUTH_STATE_COOKIE) or ""
    body_state = data.state or ""
    if not cookie_state or not body_state or not _hmac.compare_digest(cookie_state, body_state):
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="OAuth state mismatch. Please start sign-in again from the login page.",
        )
    # Burn the cookie so it can't be replayed.
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
        )

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
        )

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
    user = await service.upsert_google_user(
        google_sub=str(google_sub),
        email=email,
        full_name=profile.get("name") or email.split("@")[0],
        avatar_url=profile.get("picture"),
    )

    # Attach to default tenant if the user is brand new (no tenant memberships).
    existing_membership = await db.execute(
        select(TenantUser).where(TenantUser.user_id == user.id)
    )
    if existing_membership.scalar_one_or_none() is None:
        tenant_slug = getattr(request.state, "tenant_slug_hint", None) or "default"
        result = await db.execute(
            select(Tenant).where(Tenant.slug == tenant_slug)
        )
        tenant = result.scalar_one_or_none()
        if tenant:
            db.add(
                TenantUser(
                    user_id=user.id,
                    tenant_id=tenant.id,
                    role="member",
                    is_primary=True,
                )
            )

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


@router.get("/me/tenants", response_model=List[TenantInfo])
async def get_my_tenants(
    current_user: CurrentUser,
    db: DBSession,
):
    """Get tenant memberships for the current user.

    Used by the frontend to recover tenant context when a user is
    already authenticated but has no tenant slug stored locally
    (e.g. logged in before the tenant-slug feature was deployed).
    """
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


@router.get("/users", response_model=List[UserResponse])
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
