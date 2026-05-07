"""Gmail integration routes."""

import asyncio
import hmac as _hmac
import logging
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
    GmailAliasRefreshRequest,
    GmailAliasRefreshResponse,
    GmailAuthorizeResponse,
    GmailBackfillRequest,
    GmailBackfillStatusResponse,
    GmailCallbackRequest,
    GmailConnectionResponse,
    GmailRehydrateInlineImagesRequest,
    GmailRehydrateInlineImagesResponse,
    GmailRelinkRequest,
    GmailRelinkResponse,
    GmailStatusResponse,
)
from src.integrations.gmail.service import GmailConnectionService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/integrations/gmail", tags=["gmail"])

# Hold strong references to in-flight backfill tasks. Without this, Python is
# allowed to GC the asyncio task created by `asyncio.create_task(_run())`
# before it executes — which previously stranded users in status='running'
# with started_at=NULL forever.
_BACKFILL_TASKS: set[asyncio.Task] = set()

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
    except Exception:
        # Don't fail the connect flow if Gmail rejects the profile call —
        # the first scheduler tick will seed the cursor via the old path.
        logger.exception(
            "Failed to seed Gmail sync cursor for user_id=%s", current_user.id
        )

    # Failure is non-fatal: refresh_aliases keeps last-known-good and
    # /refresh-aliases is the recovery path.
    try:
        await service.refresh_aliases(conn)
    except Exception:
        logger.exception(
            "Failed to refresh Gmail aliases for user_id=%s", current_user.id
        )
    await db.commit()

    # Kick off historical backfill in the background — returns immediately.
    try:
        await service.schedule_backfill_if_needed(conn)
    except Exception:
        logger.exception(
            "Failed to schedule Gmail backfill for user_id=%s", current_user.id
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

    task = asyncio.create_task(_run())
    _BACKFILL_TASKS.add(task)
    task.add_done_callback(_BACKFILL_TASKS.discard)

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

    Address derivation prefers ``participant_emails`` (lowercased,
    deduped, populated at write-time by the autofill listener) and only
    falls back to parsing the from/to/cc/bcc text columns for legacy
    rows that pre-date that column. Connection self-addresses (every
    GmailConnection's primary + send-as aliases) are removed before
    contact lookup so a CC'd alias of any CRM user can't capture mail
    onto that user's own self-contact — same pollution PR #202 fixed
    in the live sync path.
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

    # Build the global self-address exclusion set once. Includes every
    # active connection's primary email plus its send-as aliases.
    conn_rows = (await db.execute(
        select(GmailConnection.email, GmailConnection.aliases)
        .where(GmailConnection.revoked_at.is_(None))
    )).all()
    self_addresses: set[str] = set()
    for email, aliases in conn_rows:
        if email:
            self_addresses.add(email.lower())
        for a in aliases or []:
            if a:
                self_addresses.add(a.lower())

    def _addresses_for(row) -> list[str]:
        # Use the cached, GIN-indexed participant list when present —
        # already lowercased + deduped at write time. Fall back to
        # parsing the human-readable address columns for legacy rows
        # that pre-date the participant_emails autofill.
        participants = list(getattr(row, "participant_emails", None) or [])
        if not participants:
            participants.extend(_parse_address_list(getattr(row, "from_email", "") or ""))
            participants.extend(_parse_address_list(getattr(row, "to_email", "") or ""))
            participants.extend(_parse_address_list(getattr(row, "cc", "") or ""))
            participants.extend(_parse_address_list(getattr(row, "bcc", "") or ""))
        if self_addresses:
            participants = [a for a in participants if a.lower() not in self_addresses]
        return participants

    async def _process_rows(rows: list, dry_run: bool) -> tuple[int, int]:
        lnk = skp = 0
        for row in rows:
            # NOTE: find_contact_id_by_any_email issues one DB query per row
            # (N+1). Acceptable for an infrequent admin backfill; a future
            # improvement could batch-resolve addresses in one query per batch.
            addresses = _addresses_for(row)
            if not addresses:
                skp += 1
                continue
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


@router.post("/refresh-aliases", response_model=GmailAliasRefreshResponse)
async def gmail_refresh_aliases(
    body: GmailAliasRefreshRequest,
    db: DBSession,
    _admin: Annotated[object, Depends(get_current_superuser)],
) -> GmailAliasRefreshResponse:
    """Admin-only: pull verified send-as aliases for every active connection.

    Skips rows that already have aliases unless ``force=True``. Commits
    per row so `refreshed` reflects only what actually persisted.
    """
    import httpx
    from sqlalchemy import select

    from src.integrations.gmail.client import GmailAuthError
    from src.integrations.gmail.models import GmailConnection

    q = select(GmailConnection).where(GmailConnection.revoked_at.is_(None))
    if body.user_id is not None:
        q = q.where(GmailConnection.user_id == body.user_id)
    rows = (await db.execute(q)).scalars().all()

    refreshed: list[dict] = []
    failures: list[dict] = []
    skipped = 0

    service = GmailConnectionService(db)
    for conn in rows:
        if not body.force and conn.aliases:
            skipped += 1
            continue

        reason: str | None = None
        try:
            aliases = await service.refresh_aliases(conn)
        except GmailAuthError as exc:
            reason = f"auth_revoked:{exc}"
        except httpx.HTTPStatusError as exc:
            reason = f"http_{exc.response.status_code}"
        except Exception as exc:
            logger.exception(
                "[gmail_alias_refresh] user_id=%s unexpected failure", conn.user_id
            )
            reason = f"unknown:{type(exc).__name__}"

        if reason is not None:
            await db.rollback()
            failures.append({"user_id": conn.user_id, "reason": reason})
            continue

        try:
            await db.commit()
        except Exception as exc:
            logger.exception(
                "[gmail_alias_refresh] user_id=%s commit failed", conn.user_id
            )
            await db.rollback()
            failures.append(
                {"user_id": conn.user_id, "reason": f"commit_failed:{type(exc).__name__}"}
            )
            continue

        refreshed.append({"user_id": conn.user_id, "aliases": aliases})

    return GmailAliasRefreshResponse(
        refreshed=refreshed, skipped=skipped, failed=failures
    )


@router.post(
    "/rehydrate-inline-images",
    response_model=GmailRehydrateInlineImagesResponse,
)
async def gmail_rehydrate_inline_images(
    body: GmailRehydrateInlineImagesRequest,
    db: DBSession,
    http_factory: GmailHttpFactory,
    _admin: Annotated[object, Depends(get_current_superuser)],
) -> GmailRehydrateInlineImagesResponse:
    """Admin-only: re-fetch existing inbound emails whose body_html still
    contains ``cid:`` references and rewrite them to embedded data: URIs.

    Background: until PR-NEXT, the Gmail sync pipeline only extracted
    text bodies and ignored attachments — so any HTML email with an
    inline image rendered as a broken image in the EmailThread view.
    The forward-going sync now substitutes inline images at write time.
    This endpoint applies the same substitution to historical rows
    that pre-date that fix by re-fetching the original Gmail message.

    Per-row behavior:
      1. Look up the inbound row's Gmail message id
         (resend_email_id parses as ``gmail:<id>``).
      2. Find the connection that owns the mailbox the row was
         received on (matches the row's ``to_email`` against
         GmailConnection.email).
      3. Refetch the full message via Gmail's messages.get.
      4. Re-parse — the new ``_parse_message`` runs the cid→data:
         substitution and returns rewritten body_html plus
         attachments metadata.
      5. UPDATE the row only if body_html actually changed.

    Skipped if the connection is revoked (we can't refetch), if the
    row's body_html doesn't contain any ``cid:``, or if Gmail returns
    a non-existent / deleted message. Each per-row error is counted
    in ``failed``; the loop continues so one bad message doesn't
    block the rest.
    """
    import contextlib

    from sqlalchemy import and_, select

    from src.email.models import InboundEmail
    from src.integrations.gmail.client import GmailClient
    from src.integrations.gmail.models import GmailConnection

    limit = max(1, min(body.limit, 20_000))

    # Build a {connection_email_lower → GmailConnection} index up front
    # so we don't re-query the connection table per row.
    conn_rows = (await db.execute(
        select(GmailConnection).where(GmailConnection.revoked_at.is_(None))
    )).scalars().all()
    if body.user_id is not None:
        conn_rows = [c for c in conn_rows if c.user_id == body.user_id]
    conn_by_email: dict[str, GmailConnection] = {}
    for c in conn_rows:
        if c.email:
            conn_by_email[c.email.lower()] = c

    if not conn_by_email:
        return GmailRehydrateInlineImagesResponse(
            scanned=0, rehydrated=0, skipped=0, failed=0, dry_run=body.dry_run
        )

    # Pull candidate rows: inbound emails whose body_html still
    # contains a ``cid:`` reference. Postgres LIKE is fine here — the
    # column is text, the substring is short, and this is admin-only
    # plumbing that runs once per outage.
    filters = [InboundEmail.body_html.ilike("%cid:%")]
    if body.user_id is not None:
        scoped_emails = list(conn_by_email.keys())
        if not scoped_emails:
            return GmailRehydrateInlineImagesResponse(
                scanned=0, rehydrated=0, skipped=0, failed=0, dry_run=body.dry_run
            )
        # Filter inbound rows to those addressed to this user's mailbox.
        from sqlalchemy import func as sa_func
        filters.append(sa_func.lower(InboundEmail.to_email).in_(scoped_emails))

    rows = (await db.execute(
        select(InboundEmail)
        .where(and_(*filters))
        .order_by(InboundEmail.id.desc())
        .limit(limit)
    )).scalars().all()

    scanned = 0
    rehydrated = 0
    skipped = 0
    failed = 0

    # Cache one GmailClient per connection so a 50-row backfill against
    # a single mailbox doesn't open 50 httpx clients.
    clients: dict[int, GmailClient] = {}
    try:
        for row in rows:
            scanned += 1
            to_email = (row.to_email or "").lower()
            conn = conn_by_email.get(to_email)
            if conn is None:
                skipped += 1
                continue

            # resend_email_id was minted as ``gmail:<message_id>`` by
            # _store_inbound. Older rows that came from Resend webhooks
            # use a different prefix; skip those.
            rid = row.resend_email_id or ""
            if not rid.startswith("gmail:"):
                skipped += 1
                continue
            gmail_msg_id = rid[len("gmail:"):]

            client = clients.get(conn.user_id)
            if client is None:
                client = GmailClient(conn, db)
                await client.__aenter__()
                clients[conn.user_id] = client

            try:
                fresh = await client.get_message(gmail_msg_id)
            except Exception as exc:
                logger.warning(
                    "[rehydrate_inline] fetch failed for inbound id=%s gmail=%s: %s",
                    row.id, gmail_msg_id, exc,
                )
                failed += 1
                continue

            new_html = fresh.get("body_html")
            new_attachments = fresh.get("attachments") or []
            if not new_html or new_html == row.body_html:
                # Re-fetch returned identical or empty HTML — nothing to
                # change. Still count it as scanned + skipped.
                skipped += 1
                continue

            if not body.dry_run:
                row.body_html = new_html
                if new_attachments and not row.attachments:
                    row.attachments = {"items": new_attachments}
                db.add(row)
            rehydrated += 1
    finally:
        for c in clients.values():
            with contextlib.suppress(Exception):
                await c.__aexit__(None, None, None)

    if not body.dry_run and rehydrated:
        await db.commit()

    return GmailRehydrateInlineImagesResponse(
        scanned=scanned,
        rehydrated=rehydrated,
        skipped=skipped,
        failed=failed,
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
