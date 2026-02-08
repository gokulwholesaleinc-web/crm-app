"""Email API routes."""

import base64
from fastapi import APIRouter, Query
from fastapi.responses import Response, RedirectResponse
from typing import Optional

from src.core.router_utils import DBSession, CurrentUser, calculate_pages, raise_not_found
from src.email.schemas import (
    SendEmailRequest,
    SendTemplateEmailRequest,
    SendCampaignEmailRequest,
    EmailQueueResponse,
    EmailListResponse,
)
from src.email.service import EmailService

router = APIRouter(prefix="/api/email", tags=["email"])

# 1x1 transparent GIF for tracking pixel
TRACKING_PIXEL = base64.b64decode(
    "R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
)


@router.post("/send", response_model=EmailQueueResponse, status_code=201)
async def send_email(
    request: SendEmailRequest,
    current_user: CurrentUser,
    db: DBSession,
):
    """Send a single email."""
    service = EmailService(db)
    email = await service.queue_email(
        to_email=request.to_email,
        subject=request.subject,
        body=request.body,
        sent_by_id=current_user.id,
        entity_type=request.entity_type,
        entity_id=request.entity_id,
    )
    return EmailQueueResponse.model_validate(email)


@router.post("/send-template", response_model=EmailQueueResponse, status_code=201)
async def send_template_email(
    request: SendTemplateEmailRequest,
    current_user: CurrentUser,
    db: DBSession,
):
    """Send an email using a template."""
    service = EmailService(db)
    email = await service.send_template_email(
        to_email=request.to_email,
        template_id=request.template_id,
        variables=request.variables,
        sent_by_id=current_user.id,
        entity_type=request.entity_type,
        entity_id=request.entity_id,
    )
    return EmailQueueResponse.model_validate(email)


@router.post("/send-campaign", status_code=201)
async def send_campaign_emails(
    request: SendCampaignEmailRequest,
    current_user: CurrentUser,
    db: DBSession,
):
    """Send emails to all pending campaign members."""
    service = EmailService(db)
    emails = await service.send_campaign_emails(
        campaign_id=request.campaign_id,
        sent_by_id=current_user.id,
    )
    return {
        "sent": len(emails),
        "emails": [EmailQueueResponse.model_validate(e) for e in emails],
    }


@router.get("", response_model=EmailListResponse)
async def list_emails(
    current_user: CurrentUser,
    db: DBSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    status: Optional[str] = None,
):
    """List emails with pagination and filters."""
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
    """Track email open via tracking pixel (no auth required)."""
    service = EmailService(db)
    await service.record_open(email_id)
    return Response(content=TRACKING_PIXEL, media_type="image/gif")


@router.get("/track/{email_id}/click")
async def track_click(
    email_id: int,
    db: DBSession,
    url: str = Query(..., description="Redirect URL"),
):
    """Track email click and redirect (no auth required)."""
    service = EmailService(db)
    await service.record_click(email_id)
    return RedirectResponse(url=url, status_code=302)


@router.get("/{email_id}", response_model=EmailQueueResponse)
async def get_email(
    email_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Get a single email by ID."""
    service = EmailService(db)
    email = await service.get_by_id(email_id)
    if not email:
        raise_not_found("Email", email_id)
    return EmailQueueResponse.model_validate(email)
