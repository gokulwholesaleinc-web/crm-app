"""Email API routes."""

import base64
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import RedirectResponse, Response
from svix.webhooks import Webhook, WebhookVerificationError

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
    SendCampaignEmailRequest,
    SendEmailRequest,
    SendTemplateEmailRequest,
    ThreadEmailItem,
    ThreadResponse,
)
from src.email.service import EmailService
from src.email.throttle import EmailThrottleService

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
    service = EmailService(db)
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


@router.post("/inbound-webhook", status_code=200)
async def inbound_webhook(request: Request, db: DBSession):
    """Receive inbound email webhook from Resend.

    Verifies svix signature, stores the email, and auto-matches to contact.
    """
    from src.config import settings as app_settings

    body = await request.body()
    headers = request.headers

    # Verify svix signature — require webhook secret to be configured
    if not app_settings.RESEND_WEBHOOK_SECRET:
        raise HTTPException(status_code=503, detail="Webhook secret not configured")

    try:
        wh = Webhook(app_settings.RESEND_WEBHOOK_SECRET)
        wh.verify(body, {
            "svix-id": headers.get("svix-id", ""),
            "svix-timestamp": headers.get("svix-timestamp", ""),
            "svix-signature": headers.get("svix-signature", ""),
        })
    except WebhookVerificationError as e:
        logger.warning("Webhook signature verification failed: %s", e)
        raise HTTPException(status_code=400, detail="Invalid webhook signature") from e

    payload = await request.json()
    event_type = payload.get("type", "")

    if event_type != "email.received":
        return {"status": "ignored", "type": event_type}

    data = payload.get("data", {})
    email_id = data.get("email_id") or data.get("id", "")

    # Fetch full email body from Resend API if email_id is available
    body_html = data.get("html")
    body_text = data.get("text")
    if email_id and not body_html and app_settings.RESEND_API_KEY:
        try:
            import resend  # pyright: ignore[reportMissingImports]
            resend.api_key = app_settings.RESEND_API_KEY
            full_email = resend.Emails.get(email_id)
            body_html = getattr(full_email, "html", None) or body_html
            body_text = getattr(full_email, "text", None) or body_text
        except Exception as e:
            logger.warning("Failed to fetch full email from Resend: %s", e)

    from_email = data.get("from", "")
    to_raw = data.get("to", "")
    to_email = to_raw[0] if isinstance(to_raw, list) else to_raw
    cc_list = data.get("cc", [])
    cc = ", ".join(cc_list) if cc_list else None

    service = EmailService(db)
    inbound = await service.store_inbound_email(
        resend_email_id=email_id or f"webhook-{datetime.now(UTC).timestamp()}",
        from_email=from_email,
        to_email=to_email,
        subject=data.get("subject", "(no subject)"),
        received_at=datetime.now(UTC),
        cc=cc,
        body_text=body_text,
        body_html=body_html,
        message_id=data.get("message_id"),
        in_reply_to=data.get("in_reply_to"),
        attachments=data.get("attachments"),
    )

    return {"status": "processed", "inbound_email_id": inbound.id}


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
    return email
