"""Mailchimp connection + campaign-stats endpoints.

All routes require an authenticated user. Connection is tenant-scoped
through the user's primary tenant — the same convention the white-label
settings router uses.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from src.core.constants import HTTPStatus
from src.core.router_utils import CurrentUser, DBSession
from src.integrations.mailchimp.client import MailchimpError
from src.integrations.mailchimp.schemas import (
    MailchimpAudience,
    MailchimpConnectRequest,
    MailchimpSetAudienceRequest,
    MailchimpStatsResponse,
    MailchimpStatus,
)
from src.integrations.mailchimp.service import (
    MailchimpNotConnected,
    MailchimpService,
)

router = APIRouter(prefix="/api/integrations/mailchimp", tags=["mailchimp"])


async def _user_tenant_id(db, user_id: int) -> int:
    from src.whitelabel.service import TenantUserService

    primary = await TenantUserService(db).get_primary_tenant(user_id)
    if primary is None:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="Current user has no primary tenant",
        )
    return primary.tenant_id


@router.get("/status", response_model=MailchimpStatus)
async def get_status(db: DBSession, current_user: CurrentUser) -> MailchimpStatus:
    tenant_id = await _user_tenant_id(db, current_user.id)
    conn = await MailchimpService(db).get_connection(tenant_id)
    if conn is None:
        return MailchimpStatus(connected=False)
    return MailchimpStatus(
        connected=True,
        server_prefix=conn.server_prefix,
        account_email=conn.account_email,
        account_login_id=conn.account_login_id,
        default_audience_id=conn.default_audience_id,
        default_audience_name=conn.default_audience_name,
        connected_at=conn.connected_at,
    )


@router.post("/connect", response_model=MailchimpStatus)
async def connect(
    payload: MailchimpConnectRequest,
    db: DBSession,
    current_user: CurrentUser,
) -> MailchimpStatus:
    tenant_id = await _user_tenant_id(db, current_user.id)
    try:
        conn = await MailchimpService(db).connect(
            tenant_id=tenant_id,
            connected_by_id=current_user.id,
            api_key=payload.api_key,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST, detail=str(exc)
        ) from exc
    except MailchimpError as exc:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=f"Mailchimp rejected the API key: {exc}",
        ) from exc
    await db.commit()
    return MailchimpStatus(
        connected=True,
        server_prefix=conn.server_prefix,
        account_email=conn.account_email,
        account_login_id=conn.account_login_id,
        default_audience_id=conn.default_audience_id,
        default_audience_name=conn.default_audience_name,
        connected_at=conn.connected_at,
    )


@router.delete("/disconnect")
async def disconnect(db: DBSession, current_user: CurrentUser) -> dict:
    tenant_id = await _user_tenant_id(db, current_user.id)
    revoked = await MailchimpService(db).disconnect(tenant_id)
    await db.commit()
    return {"disconnected": revoked}


@router.get("/audiences", response_model=list[MailchimpAudience])
async def list_audiences(
    db: DBSession, current_user: CurrentUser
) -> list[MailchimpAudience]:
    tenant_id = await _user_tenant_id(db, current_user.id)
    try:
        rows = await MailchimpService(db).list_audiences(tenant_id)
    except MailchimpNotConnected as exc:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST, detail=str(exc)
        ) from exc
    return [MailchimpAudience(**row) for row in rows]


@router.post("/audiences/select", response_model=MailchimpStatus)
async def set_default_audience(
    payload: MailchimpSetAudienceRequest,
    db: DBSession,
    current_user: CurrentUser,
) -> MailchimpStatus:
    tenant_id = await _user_tenant_id(db, current_user.id)
    try:
        conn = await MailchimpService(db).set_default_audience(
            tenant_id, payload.audience_id
        )
    except MailchimpNotConnected as exc:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST, detail=str(exc)
        ) from exc
    except MailchimpError as exc:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST, detail=str(exc)
        ) from exc
    await db.commit()
    return MailchimpStatus(
        connected=True,
        server_prefix=conn.server_prefix,
        account_email=conn.account_email,
        account_login_id=conn.account_login_id,
        default_audience_id=conn.default_audience_id,
        default_audience_name=conn.default_audience_name,
        connected_at=conn.connected_at,
    )


@router.post(
    "/campaigns/{campaign_id}/sync-stats",
    response_model=MailchimpStatsResponse,
)
async def sync_campaign_stats(
    campaign_id: int,
    db: DBSession,
    current_user: CurrentUser,
) -> MailchimpStatsResponse:
    from sqlalchemy import select

    from src.campaigns.models import Campaign
    from src.whitelabel.service import TenantUserService

    tenant_id = await _user_tenant_id(db, current_user.id)
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()
    if campaign is None:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Campaign not found"
        )
    # Ownership check — the campaign owner must belong to the caller's
    # tenant. Without this, /sync-stats/{id} accepts any campaign id and
    # leaks the (otherwise unguessable) mailchimp_campaign_id back to
    # the caller; Mailchimp itself rejects the report fetch on a foreign
    # account, but we shouldn't rely on that as the only barrier.
    owner_tenant: int | None = None
    if campaign.owner_id is not None:
        primary = await TenantUserService(db).get_primary_tenant(campaign.owner_id)
        owner_tenant = primary.tenant_id if primary else None
    if owner_tenant != tenant_id:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Campaign not found"
        )
    if not campaign.mailchimp_campaign_id:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="Campaign has not yet been sent via Mailchimp",
        )
    try:
        stats = await MailchimpService(db).sync_stats(
            campaign=campaign, tenant_id=tenant_id
        )
    except MailchimpNotConnected as exc:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST, detail=str(exc)
        ) from exc
    except MailchimpError as exc:
        raise HTTPException(
            status_code=502, detail=str(exc)
        ) from exc
    await db.commit()
    return MailchimpStatsResponse(**stats)
