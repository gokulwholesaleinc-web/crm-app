"""Marketing admin connect-flow (E1) — admin-only, feature-flagged writes.

The self-serve admin surface that lets an admin wire a client's platform
account into the warehouse and trigger a sync. Phase-1 uses a **paste-token**
flow (admin pastes an OAuth access/refresh token or, for PageSpeed, nothing —
its key is a server env var); the separate "Connect Google Marketing" OAuth
client is a human/approval task (C3) and lands later behind the same router.

Security: every route is ``require_admin`` + ``MKTG_ENABLED``. Pasted tokens are
encrypted at rest immediately (``crypto`` / ``MARKETING_TOKEN_KEY``, fail-closed);
the plaintext never touches the DB and is never echoed back. Disconnect
hard-deletes the ciphertext (E7). Every credential mutation writes a
``MarketingCredentialAudit`` row — never the token value (B1).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, select

from src.auth.models import User
from src.core.constants import HTTPStatus
from src.core.permissions import require_admin
from src.core.router_utils import DBSession

from . import cache, crypto
from .identifiers import normalize_external_account_id, normalize_manager_account_id
from .ingest import run_connection_sync, settling
from .models import (
    CREDENTIAL_MODES,
    PLATFORMS,
    AdsDailyMetric,
    AnalyticsDaily,
    MarketingAdGroup,
    MarketingCampaign,
    MarketingCredentialAudit,
    MarketingRawPayload,
    MarketingSyncRun,
    PlatformConnection,
    SiteHealthSnapshot,
)

# Warehouse data tables purged on disconnect (E7) — facts, landing + dims. Audit,
# sync-run history and the (disabled) connection row are kept for the record.
_PURGE_MODELS = (
    AdsDailyMetric,
    AnalyticsDaily,
    SiteHealthSnapshot,
    MarketingRawPayload,
    MarketingCampaign,
    MarketingAdGroup,
)
from .router import require_mktg_enabled
from .scheduler_hook import DAILY_LOOKBACK_DAYS

router = APIRouter(prefix="/api/marketing/admin", tags=["marketing-admin"])

AdminUser = Annotated[User, Depends(require_admin)]
MktgEnabled = Annotated[None, Depends(require_mktg_enabled)]


class ConnectionCreate(BaseModel):
    platform: str
    external_account_id: str = Field(min_length=1)
    access_token: str | None = None
    refresh_token: str | None = None
    credential_mode: str = "agency_oauth"
    display_name: str | None = None
    currency: str | None = Field(default=None, max_length=3)
    reporting_timezone: str = "UTC"
    manager_account_id: str | None = None
    conversion_window_days: int | None = Field(default=None, ge=1, le=90)


class ConnectionUpdate(BaseModel):
    access_token: str | None = None
    refresh_token: str | None = None
    display_name: str | None = None
    currency: str | None = Field(default=None, max_length=3)
    reporting_timezone: str | None = None
    manager_account_id: str | None = None
    conversion_window_days: int | None = Field(default=None, ge=1, le=90)
    is_enabled: bool | None = None


class ConnectionAdmin(BaseModel):
    """A connection as the admin sees it — health + config, NEVER the token."""

    id: int
    company_id: int
    platform: str
    external_account_id: str
    display_name: str | None = None
    credential_mode: str
    currency: str | None = None
    reporting_timezone: str
    conversion_window_days: int
    status: str
    last_synced_at: datetime | None = None
    last_error: str | None = None
    failure_count: int
    is_enabled: bool
    has_token: bool

    @classmethod
    def of(cls, c: PlatformConnection) -> ConnectionAdmin:
        return cls(
            id=c.id,
            company_id=c.company_id,
            platform=c.platform,
            external_account_id=c.external_account_id,
            display_name=c.display_name,
            credential_mode=c.credential_mode,
            currency=c.currency,
            reporting_timezone=c.reporting_timezone,
            conversion_window_days=c.conversion_window_days,
            status=c.status,
            last_synced_at=c.last_synced_at,
            last_error=c.last_error,
            failure_count=c.failure_count,
            is_enabled=c.is_enabled,
            has_token=c.access_token_ciphertext is not None,
        )


class RefreshResult(BaseModel):
    connection_id: int
    runs: list[str]  # "daily:success", "settling:error", ...
    status: str  # worst run status: success | partial | error


def _audit(session, connection: PlatformConnection, *, action: str, user_id: int, detail: str | None = None) -> None:
    session.add(
        MarketingCredentialAudit(
            connection_id=connection.id,
            company_id=connection.company_id,
            platform=connection.platform,
            actor_type="admin",
            actor_user_id=user_id,
            action=action,
            detail=detail,
        )
    )


def _set_token(connection: PlatformConnection, access_token: str | None, refresh_token: str | None) -> None:
    """Encrypt + store pasted tokens (fail-closed). Empty string clears nothing."""
    if access_token:
        ct, version = crypto.encrypt_token(access_token)
        connection.access_token_ciphertext = ct
        connection.token_key_version = version
    if refresh_token:
        rct, _ = crypto.encrypt_token(refresh_token)
        connection.refresh_token_ciphertext = rct


@router.post("/companies/{company_id}/connections", response_model=ConnectionAdmin, status_code=HTTPStatus.CREATED)
async def create_connection(
    company_id: int,
    body: ConnectionCreate,
    current_user: AdminUser,
    db: DBSession,
    _: MktgEnabled,
) -> ConnectionAdmin:
    """Wire a client's platform account into the warehouse (E1 paste-token)."""
    if body.platform not in PLATFORMS:
        raise HTTPException(HTTPStatus.UNPROCESSABLE_ENTITY, f"unknown platform '{body.platform}'")
    if body.credential_mode not in CREDENTIAL_MODES:
        raise HTTPException(HTTPStatus.UNPROCESSABLE_ENTITY, f"unknown credential_mode '{body.credential_mode}'")

    from src.companies.models import Company

    if (await db.execute(select(Company.id).where(Company.id == company_id))).scalar_one_or_none() is None:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Company not found")

    external = normalize_external_account_id(body.platform, body.external_account_id)
    if not external:
        raise HTTPException(HTTPStatus.UNPROCESSABLE_ENTITY, "external_account_id is empty after normalization")

    # Reject a duplicate identity up front (clearer than a raw IntegrityError).
    dupe = await db.execute(
        select(PlatformConnection.id).where(
            PlatformConnection.company_id == company_id,
            PlatformConnection.platform == body.platform,
            PlatformConnection.external_account_id == external,
        )
    )
    if dupe.scalar_one_or_none() is not None:
        raise HTTPException(HTTPStatus.CONFLICT, "A connection for this account already exists")

    connection = PlatformConnection(
        company_id=company_id,
        platform=body.platform,
        external_account_id=external,
        credential_mode=body.credential_mode,
        display_name=body.display_name,
        currency=body.currency,
        reporting_timezone=body.reporting_timezone or "UTC",
        manager_account_id=normalize_manager_account_id(body.manager_account_id),
        conversion_window_days=body.conversion_window_days or 30,
        status="pending",
    )
    _set_token(connection, body.access_token, body.refresh_token)
    db.add(connection)
    await db.flush()
    _audit(db, connection, action="create", user_id=current_user.id, detail=f"{body.platform}:{external}")
    await db.commit()
    await db.refresh(connection)
    return ConnectionAdmin.of(connection)


@router.get("/companies/{company_id}/connections", response_model=list[ConnectionAdmin])
async def list_connections(
    company_id: int,
    current_user: AdminUser,
    db: DBSession,
    _: MktgEnabled,
) -> list[ConnectionAdmin]:
    """All of a client's connections + health (never the token value)."""
    rows = await db.execute(
        select(PlatformConnection)
        .where(PlatformConnection.company_id == company_id)
        .order_by(PlatformConnection.platform, PlatformConnection.id)
    )
    return [ConnectionAdmin.of(c) for c in rows.scalars().all()]


@router.patch("/connections/{connection_id}", response_model=ConnectionAdmin)
async def update_connection(
    connection_id: int,
    body: ConnectionUpdate,
    current_user: AdminUser,
    db: DBSession,
    _: MktgEnabled,
) -> ConnectionAdmin:
    """Edit config / rotate a pasted token / pause a connection."""
    connection = await db.get(PlatformConnection, connection_id)
    if connection is None:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Connection not found")
    if body.display_name is not None:
        connection.display_name = body.display_name
    if body.currency is not None:
        connection.currency = body.currency
    if body.reporting_timezone is not None:
        connection.reporting_timezone = body.reporting_timezone
    if body.manager_account_id is not None:
        connection.manager_account_id = normalize_manager_account_id(body.manager_account_id)
    if body.conversion_window_days is not None:
        connection.conversion_window_days = body.conversion_window_days
    if body.is_enabled is not None:
        connection.is_enabled = body.is_enabled
    token_rotated = bool(body.access_token or body.refresh_token)
    if token_rotated:
        _set_token(connection, body.access_token, body.refresh_token)
        # A freshly pasted token clears a prior needs_reauth so the next sync retries.
        if connection.status == "needs_reauth":
            connection.status = "pending"
        connection.failure_count = 0
    await db.flush()
    if token_rotated:
        _audit(db, connection, action="rotate", user_id=current_user.id)
    await db.commit()
    await db.refresh(connection)
    return ConnectionAdmin.of(connection)


@router.post("/connections/{connection_id}/refresh", response_model=RefreshResult)
async def refresh_connection(
    connection_id: int,
    current_user: AdminUser,
    db: DBSession,
    _: MktgEnabled,
) -> RefreshResult:
    """Sync now: run the daily lookback (+ settling for ad platforms), then
    invalidate the client's cached reads so the dashboard updates immediately."""
    connection = await db.get(PlatformConnection, connection_id)
    if connection is None:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Connection not found")

    today = date.today()
    daily_end = today - timedelta(days=1)
    daily_start = daily_end - timedelta(days=DAILY_LOOKBACK_DAYS - 1)
    runs: list[MarketingSyncRun] = [
        await run_connection_sync(
            db, connection, run_type="daily", window_start=daily_start, window_end=daily_end
        )
    ]
    if settling.needs_settling(connection):
        s_start, s_end = settling.settling_window(connection, today=today)
        runs.append(
            await run_connection_sync(
                db, connection, run_type="settling", window_start=s_start, window_end=s_end
            )
        )
    await db.commit()
    await cache.invalidate(connection.company_id)

    statuses = [r.status for r in runs]
    overall = "error" if all(s == "error" for s in statuses) else (
        "partial" if "error" in statuses else "success"
    )
    return RefreshResult(
        connection_id=connection_id,
        runs=[f"{r.run_type}:{r.status}" for r in runs],
        status=overall,
    )


@router.delete("/connections/{connection_id}", status_code=HTTPStatus.NO_CONTENT)
async def disconnect_connection(
    connection_id: int,
    current_user: AdminUser,
    db: DBSession,
    _: MktgEnabled,
) -> Response:
    """Disconnect a client (E7): hard-delete the encrypted tokens, purge the
    warehouse facts + landing payloads, and disable the connection.

    The connection row + its credential-audit trail are KEPT (the audit FK cascades
    on a row delete, which would erase the very record of who disconnected) — the
    row is marked ``disabled`` with its tokens nulled. Provider-side token
    revocation is a follow-up once the OAuth connect flow lands (C3).
    """
    connection = await db.get(PlatformConnection, connection_id)
    if connection is None:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Connection not found")

    # Hard-delete the tokens (E7).
    connection.access_token_ciphertext = None
    connection.refresh_token_ciphertext = None
    connection.token_key_version = None
    connection.status = "disabled"
    connection.is_enabled = False

    # Purge the warehouse data for this connection (E7).
    for model in _PURGE_MODELS:
        await db.execute(delete(model).where(model.connection_id == connection_id))

    _audit(db, connection, action="revoke", user_id=current_user.id, detail=connection.platform)
    await db.commit()
    await cache.invalidate(connection.company_id)
    return Response(status_code=HTTPStatus.NO_CONTENT)
