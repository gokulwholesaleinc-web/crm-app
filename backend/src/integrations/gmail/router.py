"""Gmail integration routes."""

import hmac as _hmac
import secrets
from datetime import UTC
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from src.auth.dependencies import get_current_superuser
from src.config import settings
from src.core.constants import HTTPStatus
from src.core.router_utils import CurrentUser, DBSession
from src.integrations.gmail import oauth as gmail_oauth
from src.integrations.gmail.schemas import (
    GmailAuthorizeResponse,
    GmailBackfillRequest,
    GmailBackfillStatusResponse,
    GmailCallbackRequest,
    GmailConnectionResponse,
    GmailRelinkRequest,
    GmailRelinkResponse,
    GmailStatusResponse,
)
from src.integrations.gmail.service import GmailConnectionService

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
        ) from exc

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

    # Kick off historical backfill in the background — returns immediately.
    try:
        await service.schedule_backfill_if_needed(conn)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning(
            "Failed to schedule Gmail backfill for user_id=%s: %s",
            current_user.id, exc,
        )
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

    # Decide the state. A revoked connection paired with an auth-related
    # last_error means Google invalidated us and the user needs to
    # re-OAuth. A revoked connection with no error means manual disconnect.
    if not conn:
        return GmailStatusResponse(state="disconnected", connected=False)

    last_error = sync_state.last_error if sync_state else None
    if not conn.is_active:
        state_str = (
            "needs_reconnect"
            if last_error and "GmailAuthError" in last_error
            else "disconnected"
        )
        return GmailStatusResponse(
            state=state_str,
            connected=False,
            email=conn.email,
            last_synced_at=sync_state.last_synced_at if sync_state else None,
            last_error=last_error,
        )

    return GmailStatusResponse(
        state="connected",
        connected=True,
        email=conn.email,
        last_synced_at=sync_state.last_synced_at if sync_state else None,
        last_error=last_error,
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
    from datetime import datetime

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
        elapsed = (datetime.now(UTC) - sync_state.last_synced_at).total_seconds()
        if elapsed < GMAIL_MANUAL_SYNC_COOLDOWN_SECONDS:
            raise HTTPException(
                status_code=HTTPStatus.TOO_MANY_REQUESTS,
                detail="Gmail sync just ran; wait a few seconds and try again.",
            )

    await GmailSyncWorker.sync_account(conn, db)
    return {"synced": True}


@router.post("/backfill", response_model=GmailBackfillStatusResponse)
async def gmail_backfill(
    current_user: CurrentUser,
    db: DBSession,
    body: GmailBackfillRequest = GmailBackfillRequest(),
):
    """Manually trigger a Gmail historical backfill for the current user.

    Launches the backfill as a background asyncio task so the HTTP response
    returns immediately. The UI polls GET /backfill/status for progress.
    """
    import asyncio

    from src.integrations.gmail.models import GmailBackfillState
    from src.integrations.gmail.sync import GmailSyncWorker, _get_or_create_backfill_state

    service = GmailConnectionService(db)
    conn = await service.get_by_user(current_user.id)
    if not conn or conn.revoked_at is not None:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail="No active Gmail connection",
        )

    state = await _get_or_create_backfill_state(current_user.id, db)
    if state.status == "running":
        raise HTTPException(
            status_code=HTTPStatus.TOO_MANY_REQUESTS,
            detail="Backfill already in progress",
        )

    # Atomically claim the slot here, before launching the task — otherwise
    # two concurrent POSTs both see status != 'running' and spawn duplicate
    # workers, racing through _process_message on the same message ids.
    state.status = "running"
    await db.commit()

    days = max(1, min(body.days, 3650))

    import logging

    import src.database as db_module

    logger = logging.getLogger(__name__)

    async def _run() -> None:
        try:
            async with db_module.async_session_maker() as fresh_db:
                from sqlalchemy import select as _select
                result = await fresh_db.execute(
                    _select(type(conn)).where(type(conn).user_id == current_user.id)
                )
                fresh_conn = result.scalar_one()
                await GmailSyncWorker.backfill(fresh_conn, fresh_db, days=days)
        except Exception as exc:
            # backfill() persists in-flight failures itself. This catch
            # covers session-open errors / NoResultFound / etc. so the
            # state row doesn't get stuck on 'running' forever.
            logger.exception("[gmail_backfill] outer task failed for user_id=%s: %s",
                             current_user.id, exc)
            try:
                async with db_module.async_session_maker() as failure_db:
                    from sqlalchemy import select as _sel
                    s = (await failure_db.execute(
                        _sel(GmailBackfillState).where(
                            GmailBackfillState.user_id == current_user.id
                        )
                    )).scalar_one_or_none()
                    if s is not None:
                        s.status = "failed"
                        s.error = str(exc)[:500]
                        await failure_db.commit()
            except Exception:
                logger.exception("[gmail_backfill] could not record failure state")

    asyncio.create_task(_run())

    return GmailBackfillStatusResponse(
        status="running",
        processed_count=0,
        total_count=0,
        started_at=None,
        finished_at=None,
        error=None,
    )


@router.get("/backfill/status", response_model=GmailBackfillStatusResponse)
async def gmail_backfill_status(
    current_user: CurrentUser,
    db: DBSession,
):
    """Return the current backfill progress for the authenticated user."""
    from sqlalchemy import select

    from src.integrations.gmail.models import GmailBackfillState

    result = await db.execute(
        select(GmailBackfillState).where(GmailBackfillState.user_id == current_user.id)
    )
    state = result.scalar_one_or_none()
    if state is None:
        return GmailBackfillStatusResponse(
            status="none",
            processed_count=0,
            total_count=0,
        )
    return GmailBackfillStatusResponse(
        status=state.status,
        processed_count=state.processed_count,
        total_count=state.total_count,
        started_at=state.started_at,
        finished_at=state.finished_at,
        error=state.error,
    )


@router.post("/relink", response_model=GmailRelinkResponse)
async def gmail_relink(
    body: GmailRelinkRequest,
    db: DBSession,
    _admin: Annotated[object, Depends(get_current_superuser)],
) -> GmailRelinkResponse:
    """Admin-only: backfill entity_type/entity_id on unlinked email rows.

    Walks email_queue (sent_via='gmail') and inbound_emails rows where
    entity_id IS NULL, attempts to match each row's addresses to a contact
    via find_contact_id_by_any_email, and writes the link when found.
    Safe to re-run: never overwrites a non-NULL entity_id.
    """
    from sqlalchemy import and_, select

    from src.contacts.alias_match import find_contact_id_by_any_email
    from src.email.models import EmailQueue, InboundEmail
    from src.integrations.gmail.client import _parse_address_list
    from src.integrations.gmail.models import GmailConnection

    limit = max(1, min(body.limit, 50_000))
    BATCH = 500

    scanned = 0
    linked = 0
    skipped = 0

    async def _process_rows(rows: list, dry_run: bool) -> tuple[int, int]:
        lnk = skp = 0
        for row in rows:
            # NOTE: find_contact_id_by_any_email issues one DB query per row
            # (N+1). Acceptable for an infrequent admin backfill; a future
            # improvement could batch-resolve addresses in one query per batch.
            addresses: list[str] = []
            addresses.extend(_parse_address_list(row.from_email))
            addresses.extend(_parse_address_list(row.to_email))
            addresses.extend(_parse_address_list(row.cc))
            addresses.extend(_parse_address_list(row.bcc))
            entity_type, entity_id = await find_contact_id_by_any_email(addresses, db)
            if entity_id is not None:
                if not dry_run:
                    row.entity_type = entity_type
                    row.entity_id = entity_id
                    db.add(row)
                lnk += 1
            else:
                skp += 1
        return lnk, skp

    # --- email_queue rows ---
    # Use keyset pagination (WHERE id > last_seen_id) rather than OFFSET so
    # that rows committed in previous batches (entity_id now non-NULL) don't
    # shift the result window and cause skips.
    eq_filters = [
        EmailQueue.entity_id.is_(None),
        EmailQueue.sent_via == "gmail",
    ]
    if body.user_id is not None:
        eq_filters.append(EmailQueue.sent_by_id == body.user_id)

    last_eq_id = 0
    while True:
        q = (
            select(EmailQueue)
            .where(and_(EmailQueue.id > last_eq_id, *eq_filters))
            .order_by(EmailQueue.id)
            .limit(min(BATCH, limit - scanned))
        )
        rows = (await db.execute(q)).scalars().all()
        if not rows:
            break

        scanned += len(rows)
        lnk, skp = await _process_rows(rows, body.dry_run)
        linked += lnk
        skipped += skp

        if not body.dry_run:
            await db.commit()

        last_eq_id = rows[-1].id
        if scanned >= limit or len(rows) < BATCH:
            break

    # --- inbound_emails rows ---
    ib_filters = [InboundEmail.entity_id.is_(None)]
    if body.user_id is not None:
        # Scope to the mailbox(es) owned by this user's GmailConnection.
        conn_emails = (await db.execute(
            select(GmailConnection.email).where(GmailConnection.user_id == body.user_id)
        )).scalars().all()
        if not conn_emails:
            return GmailRelinkResponse(
                scanned=scanned, linked=linked, skipped=skipped, dry_run=body.dry_run
            )
        ib_filters.append(InboundEmail.to_email.in_(conn_emails))

    last_ib_id = 0
    while scanned < limit:
        q = (
            select(InboundEmail)
            .where(and_(InboundEmail.id > last_ib_id, *ib_filters))
            .order_by(InboundEmail.id)
            .limit(min(BATCH, limit - scanned))
        )
        rows = (await db.execute(q)).scalars().all()
        if not rows:
            break

        scanned += len(rows)
        lnk, skp = await _process_rows(rows, body.dry_run)
        linked += lnk
        skipped += skp

        if not body.dry_run:
            await db.commit()

        last_ib_id = rows[-1].id
        if scanned >= limit or len(rows) < BATCH:
            break

    return GmailRelinkResponse(
        scanned=scanned,
        linked=linked,
        skipped=skipped,
        dry_run=body.dry_run,
    )


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
