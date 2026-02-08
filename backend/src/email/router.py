"""Email API routes."""

import base64
from typing import Optional

from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import Response, RedirectResponse

from src.core.constants import HTTPStatus
from src.core.router_utils import DBSession, CurrentUser, calculate_pages
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
        )
    return email


@router.post("/send-campaign", status_code=HTTPStatus.CREATED)
async def send_campaign_email(
    data: SendCampaignEmailRequest,
    current_user: CurrentUser,
    db: DBSession,
):
    """Send campaign emails to all members."""
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
        )
    return {"sent": len(emails), "items": [EmailQueueResponse.model_validate(e) for e in emails]}


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
