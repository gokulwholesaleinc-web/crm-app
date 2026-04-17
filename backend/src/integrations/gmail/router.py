"""Gmail integration routes."""

import hmac as _hmac
import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from src.config import settings
from src.core.constants import HTTPStatus
from src.core.router_utils import DBSession, CurrentUser
from src.integrations.gmail import oauth as gmail_oauth
from src.integrations.gmail.service import GmailConnectionService
from src.integrations.gmail.schemas import (
    GmailAuthorizeResponse,
    GmailCallbackRequest,
    GmailConnectionResponse,
    GmailStatusResponse,
)

router = APIRouter(prefix="/api/integrations/gmail", tags=["gmail"])

GMAIL_OAUTH_STATE_COOKIE = "crm_gmail_oauth_state"
GMAIL_OAUTH_STATE_TTL_SECONDS = 600  # 10 minutes


def get_gmail_http_factory() -> gmail_oauth.HttpClientFactory:
    return gmail_oauth.default_client_factory


GmailHttpFactory = Annotated[
    gmail_oauth.HttpClientFactory, Depends(get_gmail_http_factory)
]


@router.get("/authorize", response_model=GmailAuthorizeResponse)
async def gmail_authorize(
    response: Response,
    current_user: CurrentUser,
):
    client_id = settings.GOOGLE_CLIENT_ID
    if not client_id:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="Google integration is not configured",
        )

    state = secrets.token_urlsafe(24)
    redirect_uri = gmail_oauth.get_redirect_uri()
    # No login_hint: the Gmail account a user wants to connect is often
    # different from their CRM login email. Let Google show the picker.
    auth_url = gmail_oauth.build_authorize_url(
        client_id=client_id,
        redirect_uri=redirect_uri,
        state=state,
    )

    cross_site = not settings.DEBUG
    response.set_cookie(
        key=GMAIL_OAUTH_STATE_COOKIE,
        value=state,
        max_age=GMAIL_OAUTH_STATE_TTL_SECONDS,
        httponly=True,
        secure=cross_site,
        samesite="none" if cross_site else "lax",
        path="/",
    )
    return GmailAuthorizeResponse(auth_url=auth_url)


@router.post("/callback", response_model=GmailConnectionResponse)
async def gmail_callback(
    request: Request,
    response: Response,
    data: GmailCallbackRequest,
    current_user: CurrentUser,
    db: DBSession,
    http_factory: GmailHttpFactory,
):
    client_id = settings.GOOGLE_CLIENT_ID
    client_secret = settings.GOOGLE_CLIENT_SECRET
    if not client_id or not client_secret:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="Google integration is not configured",
        )

    cookie_state = request.cookies.get(GMAIL_OAUTH_STATE_COOKIE) or ""
    body_state = data.state or ""
    if not cookie_state or not body_state or not _hmac.compare_digest(cookie_state, body_state):
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="OAuth state mismatch. Please start the Gmail connection again.",
        )
    response.delete_cookie(GMAIL_OAUTH_STATE_COOKIE, path="/")

    redirect_uri = gmail_oauth.get_redirect_uri()
    try:
        token_data = await gmail_oauth.exchange_code_for_tokens(
            code=data.code,
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            client_factory=http_factory,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=f"Gmail token exchange failed: {str(exc)}",
        )

    id_token = token_data.get("id_token", "")
    gmail_email = gmail_oauth.decode_id_token_email(id_token) if id_token else None
    if not gmail_email:
        gmail_email = current_user.email

    service = GmailConnectionService(db, client_factory=http_factory)
    conn = await service.upsert_from_token_exchange(
        user_id=current_user.id,
        token_response=token_data,
        email=gmail_email,
    )
    # Seed the history cursor so the first background sync actually pulls
    # any reply that arrives in the seconds after connect instead of just
    # learning the starting historyId and returning empty.
    try:
        await service.seed_sync_cursor(conn)
    except Exception as exc:
        # Don't fail the connect flow if Gmail rejects the profile call —
        # the first scheduler tick will seed the cursor via the old path.
        import logging
        logging.getLogger(__name__).warning(
            "Failed to seed Gmail sync cursor for user_id=%s: %s",
            current_user.id, exc,
        )
    await db.commit()
    await db.refresh(conn)

    sync_state = await service.get_sync_state(current_user.id)
    return GmailConnectionResponse(
        id=conn.id,
        email=conn.email,
        scopes=conn.scope_list,
        is_active=conn.is_active,
        last_synced_at=sync_state.last_synced_at if sync_state else None,
        created_at=conn.created_at,
        updated_at=conn.updated_at,
    )


@router.get("/status", response_model=GmailStatusResponse)
async def gmail_status(
    current_user: CurrentUser,
    db: DBSession,
):
    service = GmailConnectionService(db)
    conn = await service.get_by_user(current_user.id)
    sync_state = await service.get_sync_state(current_user.id)

    if not conn or not conn.is_active:
        return GmailStatusResponse(connected=False)

    return GmailStatusResponse(
        connected=True,
        email=conn.email,
        last_synced_at=sync_state.last_synced_at if sync_state else None,
        last_error=sync_state.last_error if sync_state else None,
    )


GMAIL_MANUAL_SYNC_COOLDOWN_SECONDS = 15


@router.post("/sync")
async def gmail_sync(
    current_user: CurrentUser,
    db: DBSession,
):
    """Run Gmail sync for the current user immediately.

    Backs the "Sync" button on Settings → Integrations → Gmail so users
    don't have to wait for the background scheduler when they expect a
    reply to land. Guarded by a short cooldown so button-mashing can't
    race the 120s background tick or burn Gmail API quota.
    """
    from datetime import datetime, timezone
    from src.integrations.gmail.sync import GmailSyncWorker

    service = GmailConnectionService(db)
    conn = await service.get_by_user(current_user.id)
    if not conn or conn.revoked_at is not None:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail="No active Gmail connection",
        )

    sync_state = await service.get_sync_state(current_user.id)
    if sync_state and sync_state.last_synced_at:
        elapsed = (datetime.now(timezone.utc) - sync_state.last_synced_at).total_seconds()
        if elapsed < GMAIL_MANUAL_SYNC_COOLDOWN_SECONDS:
            raise HTTPException(
                status_code=HTTPStatus.TOO_MANY_REQUESTS,
                detail="Gmail sync just ran; wait a few seconds and try again.",
            )

    await GmailSyncWorker.sync_account(conn, db)
    return {"synced": True}


@router.post("/disconnect")
async def gmail_disconnect(
    current_user: CurrentUser,
    db: DBSession,
    http_factory: GmailHttpFactory,
):
    service = GmailConnectionService(db, client_factory=http_factory)
    conn = await service.mark_revoked(current_user.id)
    if not conn:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="No Gmail connection found")
    await db.commit()
    return {"disconnected": True}
