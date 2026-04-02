"""Meta (Facebook/Instagram) integration API routes."""

import hashlib
import hmac
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response
from src.core.router_utils import DBSession, CurrentUser
from src.core.constants import HTTPStatus
from src.meta.schemas import (
    MetaSyncRequest,
    CompanyMetaDataResponse,
    MetaConnectRequest,
    MetaCallbackRequest,
    MetaCredentialResponse,
    MetaConnectionStatus,
    MetaLeadCaptureResponse,
    MetaWebhookPayload,
)
from src.meta.service import MetaService

router = APIRouter(prefix="/api/meta", tags=["meta"])


# =========================================================================
# OAuth2 Flow
# =========================================================================

@router.get("/status", response_model=MetaConnectionStatus)
async def get_connection_status(
    current_user: CurrentUser,
    db: DBSession,
):
    """Get the current user's Meta connection status."""
    service = MetaService(db)
    status = await service.get_connection_status(current_user.id)
    return MetaConnectionStatus(**status)


@router.post("/connect")
async def get_auth_url(
    data: MetaConnectRequest,
    current_user: CurrentUser,
    db: DBSession,
):
    """Get Meta OAuth2 authorization URL."""
    from src.config import settings
    if not settings.META_APP_ID:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="Meta integration is not configured")

    service = MetaService(db)
    redirect_uri = data.redirect_uri or ""
    auth_url = service.get_authorization_url(redirect_uri, state=str(current_user.id))
    return {"auth_url": auth_url}


@router.post("/callback", response_model=MetaCredentialResponse)
async def handle_callback(
    data: MetaCallbackRequest,
    current_user: CurrentUser,
    db: DBSession,
):
    """Handle OAuth2 callback and store credentials."""
    service = MetaService(db)
    redirect_uri = data.redirect_uri or ""
    try:
        credential = await service.exchange_code(data.code, redirect_uri, current_user.id)
    except Exception as exc:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=f"Failed to connect: {str(exc)}")
    return MetaCredentialResponse.model_validate(credential)


@router.delete("/disconnect", status_code=HTTPStatus.NO_CONTENT)
async def disconnect(
    current_user: CurrentUser,
    db: DBSession,
):
    """Disconnect Meta integration."""
    service = MetaService(db)
    removed = await service.disconnect(current_user.id)
    if not removed:
        raise HTTPException(status_code=404, detail="No Meta connection found")


# =========================================================================
# Facebook Page Sync
# =========================================================================

@router.get("/companies/{company_id}", response_model=CompanyMetaDataResponse)
async def get_company_meta(
    company_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Get Meta data for a company."""
    service = MetaService(db)
    meta = await service.get_by_company(company_id)
    if not meta:
        raise HTTPException(status_code=404, detail="No Meta data found for this company")
    return CompanyMetaDataResponse.model_validate(meta)


@router.post("/companies/{company_id}/sync", response_model=CompanyMetaDataResponse)
async def sync_company_meta(
    company_id: int,
    request_data: MetaSyncRequest,
    current_user: CurrentUser,
    db: DBSession,
):
    """Sync Meta page data for a company."""
    service = MetaService(db)
    meta = await service.sync_page(company_id, request_data.page_id)
    return CompanyMetaDataResponse.model_validate(meta)


@router.post("/companies/{company_id}/sync-instagram", response_model=CompanyMetaDataResponse)
async def sync_instagram(
    company_id: int,
    request_data: MetaSyncRequest,
    current_user: CurrentUser,
    db: DBSession,
):
    """Sync Instagram business account data for a company (linked to Facebook page)."""
    service = MetaService(db)
    credential = await service.get_credential(current_user.id)
    if not credential or not credential.access_token:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="No Meta connection or access token")

    meta = await service.sync_instagram(company_id, request_data.page_id, credential.access_token)
    if not meta:
        raise HTTPException(status_code=404, detail="No Instagram business account linked to this page")
    return CompanyMetaDataResponse.model_validate(meta)


@router.get("/companies/{company_id}/export-csv")
async def export_meta_csv(
    company_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Export Meta data as CSV."""
    service = MetaService(db)
    csv_content = await service.export_csv(company_id)
    if not csv_content:
        raise HTTPException(status_code=404, detail="No Meta data to export")
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=meta-company-{company_id}.csv"},
    )


# =========================================================================
# Lead Capture Webhook
# =========================================================================

@router.get("/webhook")
async def verify_webhook(
    request: Request,
):
    """Meta webhook verification (hub.challenge handshake)."""
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    from src.config import settings
    verify_token = getattr(settings, "META_WEBHOOK_VERIFY_TOKEN", "crm_meta_webhook")

    if mode == "subscribe" and token == verify_token:
        return Response(content=challenge, media_type="text/plain")
    raise HTTPException(status_code=403, detail="Verification failed")


@router.post("/webhook")
async def receive_webhook(
    request: Request,
    db: DBSession,
):
    """Receive Meta Lead Ads webhook events with HMAC-SHA256 signature verification."""
    from src.config import settings

    # Verify signature if app secret is configured
    raw_body = await request.body()
    if settings.META_APP_SECRET:
        signature = request.headers.get("X-Hub-Signature-256", "")
        expected = "sha256=" + hmac.new(
            settings.META_APP_SECRET.encode(),
            raw_body,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise HTTPException(status_code=403, detail="Invalid webhook signature")

    import json
    try:
        body = json.loads(raw_body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    payload = MetaWebhookPayload(**body)
    if payload.object != "page":
        return {"status": "ignored"}

    service = MetaService(db)
    captures = await service.process_lead_webhook(payload.model_dump())
    return {"status": "ok", "leads_captured": len(captures)}


@router.get("/leads/unprocessed")
async def get_unprocessed_leads(
    current_user: CurrentUser,
    db: DBSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
):
    """Get unprocessed lead captures from Meta Lead Ads."""
    service = MetaService(db)
    captures = await service.get_unprocessed_captures(page=page, page_size=page_size)
    return [MetaLeadCaptureResponse.model_validate(c) for c in captures]
