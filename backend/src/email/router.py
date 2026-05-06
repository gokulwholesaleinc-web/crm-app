"""Email API routes."""

import base64
import logging

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse, Response

from src.core.constants import EntityNames, HTTPStatus
from src.core.router_utils import (
    CurrentUser,
    DBSession,
    calculate_pages,
    check_ownership,
    get_entity_or_404,
)
from src.email.schemas import (
    EmailListResponse,
    EmailQueueResponse,
    EmailSearchResponse,
    EmailSearchResult,
    SendCampaignEmailRequest,
    SendEmailRequest,
    SendTemplateEmailRequest,
    ThreadEmailItem,
    ThreadResponse,
)
from src.email.service import EmailService
from src.email.throttle import EmailThrottleService
from src.email.types import EmailAttachment

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/email", tags=["email"])

# 1x1 transparent GIF for tracking pixel
TRACKING_PIXEL = base64.b64decode(
    "R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
)


@router.post("/send", response_model=EmailQueueResponse, status_code=HTTPStatus.CREATED)
async def send_email(
    data: SendEmailRequest,
    current_user: CurrentUser,
    db: DBSession,
):
    """Send an email and queue it for tracking."""
    # Decode user-supplied attachments once into the in-memory form the
    # provider sender expects. Schema-level validators have already
    # range-checked size + count + base64 validity, so we can decode
    # without re-validating here. Bytes are passed straight through to
    # the provider and never land on the EmailQueue row.
    decoded_attachments: list[EmailAttachment] | None = None
    if data.attachments:
        decoded_attachments = [
            EmailAttachment(
                filename=att.filename,
                content=base64.b64decode(att.content_b64),
                content_type=att.content_type,
            )
            for att in data.attachments
        ]

    service = EmailService(db)

    # Reply-gating: forbid composing a reply to a thread the user isn't a
    # participant of. Without this an admin could reply to a colleague's
    # private inbound mail from the colleague's CRM record. The reply itself
    # still goes out from the replier's own Gmail connection — that's the
    # right thing once we've verified they were on the original thread.
    if data.reply_to_inbound_id is not None or data.reply_to_email_id is not None:
        from src.email.participants import get_user_connection_emails
        viewer_emails = set(await get_user_connection_emails(db, current_user.id))

        async def _assert_participant(participants: list[str] | None, fallback_sent_by: int | None) -> None:
            if fallback_sent_by == current_user.id:
                return
            if viewer_emails and viewer_emails.intersection(participants or []):
                return
            raise HTTPException(
                status_code=HTTPStatus.FORBIDDEN,
                detail="You can only reply to threads you are a participant of",
            )

        if data.reply_to_inbound_id is not None:
            from src.email.models import InboundEmail
            from sqlalchemy import select as _select
            row = (await db.execute(
                _select(InboundEmail.participant_emails).where(InboundEmail.id == data.reply_to_inbound_id)
            )).one_or_none()
            if row is None:
                raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Source thread not found")
            await _assert_participant(row[0], None)

        if data.reply_to_email_id is not None:
            from src.email.models import EmailQueue
            from sqlalchemy import select as _select
            row = (await db.execute(
                _select(EmailQueue.participant_emails, EmailQueue.sent_by_id).where(EmailQueue.id == data.reply_to_email_id)
            )).one_or_none()
            if row is None:
                raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Source thread not found")
            await _assert_participant(row[0], row[1])

    email = await service.queue_email(
        to_email=data.to_email,
        subject=data.subject,
        body=data.body,
        sent_by_id=current_user.id,
        entity_type=data.entity_type,
        entity_id=data.entity_id,
        from_email=data.from_email,
        cc=data.cc,
        bcc=data.bcc,
        reply_to_email_id=data.reply_to_email_id,
        reply_to_inbound_id=data.reply_to_inbound_id,
        attachments=decoded_attachments,
    )
    return email


@router.post("/send-template", response_model=EmailQueueResponse, status_code=HTTPStatus.CREATED)
async def send_template_email(
    data: SendTemplateEmailRequest,
    current_user: CurrentUser,
    db: DBSession,
):
    """Send an email using a template."""
    service = EmailService(db)
    try:
        email = await service.send_template_email(
            to_email=data.to_email,
            template_id=data.template_id,
            variables=data.variables,
            sent_by_id=current_user.id,
            entity_type=data.entity_type,
            entity_id=data.entity_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail=str(exc),
        ) from exc
    return email


@router.post("/send-campaign", status_code=HTTPStatus.CREATED)
async def send_campaign_email(
    data: SendCampaignEmailRequest,
    current_user: CurrentUser,
    db: DBSession,
):
    """Send campaign emails to all members."""
    from src.campaigns.service import CampaignService

    campaign_service = CampaignService(db)
    campaign = await get_entity_or_404(campaign_service, data.campaign_id, EntityNames.CAMPAIGN)
    check_ownership(campaign, current_user, EntityNames.CAMPAIGN)

    service = EmailService(db)
    try:
        emails = await service.send_campaign_emails(
            campaign_id=data.campaign_id,
            template_id=data.template_id,
            variables=data.variables,
            sent_by_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail=str(exc),
        ) from exc
    return {"sent": len(emails), "items": [EmailQueueResponse.model_validate(e) for e in emails]}


@router.get("/thread", response_model=ThreadResponse)
async def get_email_thread(
    current_user: CurrentUser,
    db: DBSession,
    entity_type: str = Query(..., description="Entity type (e.g. contacts)"),
    entity_id: int = Query(..., description="Entity ID"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
):
    """Get unified email thread (inbound + outbound) for an entity."""
    service = EmailService(db)
    items, total = await service.get_thread(
        entity_type=entity_type,
        entity_id=entity_id,
        page=page,
        page_size=page_size,
        viewer_user_id=current_user.id,
    )
    return ThreadResponse(
        items=[ThreadEmailItem(**item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
        pages=calculate_pages(total, page_size),
    )


@router.get("/volume-stats")
async def get_volume_stats(
    current_user: CurrentUser,
    db: DBSession,
):
    """Get email volume statistics (sent today, daily limit, warmup info)."""
    throttle = EmailThrottleService(db)
    return await throttle.get_volume_stats()


@router.get("/search", response_model=EmailSearchResponse)
async def search_emails(
    current_user: CurrentUser,
    db: DBSession,
    q: str = Query(..., min_length=1, max_length=200, description="Search query"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=50),
    entity_type: str | None = Query(None),
    entity_id: int | None = Query(None),
):
    """Search emails by keyword across subject, body, and addresses."""
    service = EmailService(db)
    items, total = await service.search_emails(
        q=q,
        user_id=current_user.id,
        page=page,
        page_size=page_size,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    return EmailSearchResponse(
        items=[EmailSearchResult(**item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
        pages=calculate_pages(total, page_size),
    )


@router.get("", response_model=EmailListResponse)
async def list_emails(
    current_user: CurrentUser,
    db: DBSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    entity_type: str | None = None,
    entity_id: int | None = None,
    status: str | None = None,
):
    """List sent emails with optional filters."""
    service = EmailService(db)
    items, total = await service.get_list(
        page=page,
        page_size=page_size,
        entity_type=entity_type,
        entity_id=entity_id,
        status=status,
        viewer_user_id=current_user.id,
    )
    return EmailListResponse(
        items=[EmailQueueResponse.model_validate(e) for e in items],
        total=total,
        page=page,
        page_size=page_size,
        pages=calculate_pages(total, page_size),
    )


@router.get("/track/{email_id}/open")
async def track_open(email_id: int, db: DBSession):
    """Track email open - returns a 1x1 transparent pixel."""
    service = EmailService(db)
    await service.record_open(email_id)
    return Response(content=TRACKING_PIXEL, media_type="image/gif")


@router.get("/track/{email_id}/click")
async def track_click(
    email_id: int,
    db: DBSession,
    url: str = Query(..., description="The destination URL"),
):
    """Track email link click and redirect to destination."""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise HTTPException(status_code=400, detail="Invalid redirect URL")
    # Block redirects to private/internal IPs
    import ipaddress
    try:
        import socket
        ip = socket.gethostbyname(parsed.hostname or "")
        if ipaddress.ip_address(ip).is_private:
            raise HTTPException(status_code=400, detail="Invalid redirect URL")
    except (socket.gaierror, ValueError):
        pass
    service = EmailService(db)
    await service.record_click(email_id)
    return RedirectResponse(url=url, status_code=302)


@router.get("/{email_id}", response_model=EmailQueueResponse)
async def get_email(
    email_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Get email details by ID."""
    service = EmailService(db)
    email = await service.get_by_id(email_id)
    if not email:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail=f"Email with ID {email_id} not found",
        )
    # Participant-based privacy: composer always sees their row; otherwise
    # the viewer must be one of the recorded participants.
    if email.sent_by_id != current_user.id:
        from src.email.participants import get_user_connection_emails
        viewer_emails = set(await get_user_connection_emails(db, current_user.id))
        if not viewer_emails.intersection(email.participant_emails or []):
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail=f"Email with ID {email_id} not found",
            )
    return email
