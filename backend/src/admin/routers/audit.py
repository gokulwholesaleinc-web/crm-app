"""Admin-only CRM audit dashboard endpoints."""

from datetime import date

from fastapi import APIRouter, Query, Request

from src.admin._router_helpers import _require_admin
from src.audit.schemas import (
    AdminAuditEntityDetail,
    AdminAuditEntitySummary,
    AdminAuditFeedItem,
    AdminAuditFeedResponse,
    AdminAuditSummaryResponse,
    AdminAuditTotals,
    AdminAuditUserDetail,
    AdminAuditUserSummary,
    WorkSessionResponse,
)
from src.audit.service import AuditService
from src.core.entity_types import canonical_plural
from src.core.router_utils import CurrentUser, DBSession, calculate_pages

router = APIRouter(prefix="/audit")


@router.get("/feed", response_model=AdminAuditFeedResponse)
async def get_admin_audit_feed(
    request: Request,
    current_user: CurrentUser,
    db: DBSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    start_date: date | None = None,
    end_date: date | None = None,
    user_id: int | None = None,
    entity_type: str | None = None,
    entity_id: int | None = None,
    action: str | None = None,
    search: str | None = None,
):
    """Filtered audit feed across the whole CRM."""
    _require_admin(current_user)
    service = AuditService(db)
    items, total = await service.get_admin_feed(
        page=page,
        page_size=page_size,
        start_date=start_date,
        end_date=end_date,
        user_id=user_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        search=search,
    )
    return AdminAuditFeedResponse(
        items=[AdminAuditFeedItem(**item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
        pages=calculate_pages(total, page_size),
    )


@router.get("/summary", response_model=AdminAuditSummaryResponse)
async def get_admin_audit_summary(
    request: Request,
    current_user: CurrentUser,
    db: DBSession,
    start_date: date | None = None,
    end_date: date | None = None,
    user_id: int | None = None,
    entity_type: str | None = None,
    action: str | None = None,
    search: str | None = None,
):
    """Summary rollups for audit, estimated active CRM time, and security signals."""
    _require_admin(current_user)
    summary = await AuditService(db).get_admin_summary(
        start_date=start_date,
        end_date=end_date,
        user_id=user_id,
        entity_type=entity_type,
        action=action,
        search=search,
    )
    return AdminAuditSummaryResponse(
        start_at=summary["start_at"],
        end_at=summary["end_at"],
        totals=AdminAuditTotals(**summary["totals"]),
        users=[AdminAuditUserSummary(**row) for row in summary["users"]],
        entities=[AdminAuditEntitySummary(**row) for row in summary["entities"]],
        security=summary["security"],
    )


@router.get("/users/{user_id}", response_model=AdminAuditUserDetail)
async def get_admin_audit_user_detail(
    user_id: int,
    request: Request,
    current_user: CurrentUser,
    db: DBSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    start_date: date | None = None,
    end_date: date | None = None,
    entity_type: str | None = None,
    action: str | None = None,
    search: str | None = None,
):
    """Audit and work-session detail for one CRM user."""
    _require_admin(current_user)
    service = AuditService(db)
    summary = await service.get_admin_summary(
        start_date=start_date,
        end_date=end_date,
        user_id=user_id,
        entity_type=entity_type,
        action=action,
        search=search,
    )
    user_summary = next(
        (AdminAuditUserSummary(**row) for row in summary["users"] if row["user_id"] == user_id),
        AdminAuditUserSummary(user_id=user_id, user_name=f"User #{user_id}"),
    )
    items, total = await service.get_admin_feed(
        page=page,
        page_size=page_size,
        start_date=start_date,
        end_date=end_date,
        user_id=user_id,
        entity_type=entity_type,
        action=action,
        search=search,
    )
    sessions = await service.get_work_sessions(
        start_date=start_date,
        end_date=end_date,
        user_id=user_id,
        entity_type=entity_type,
    )
    return AdminAuditUserDetail(
        summary=user_summary,
        feed=AdminAuditFeedResponse(
            items=[AdminAuditFeedItem(**item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
            pages=calculate_pages(total, page_size),
        ),
        sessions=[WorkSessionResponse(**session) for session in sessions],
    )


@router.get("/entities/{entity_type}/{entity_id}", response_model=AdminAuditEntityDetail)
async def get_admin_audit_entity_detail(
    entity_type: str,
    entity_id: int,
    request: Request,
    current_user: CurrentUser,
    db: DBSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    start_date: date | None = None,
    end_date: date | None = None,
    user_id: int | None = None,
    action: str | None = None,
    search: str | None = None,
):
    """Audit and work-session detail for one CRM entity."""
    _require_admin(current_user)
    service = AuditService(db)
    summary = await service.get_admin_summary(
        start_date=start_date,
        end_date=end_date,
        user_id=user_id,
        entity_type=entity_type,
        action=action,
        search=search,
    )
    entity_summary = next(
        (
            AdminAuditEntitySummary(**row)
            for row in summary["entities"]
            if row["entity_id"] == entity_id
            and canonical_plural(row["entity_type"]) == canonical_plural(entity_type)
        ),
        AdminAuditEntitySummary(entity_type=entity_type, entity_id=entity_id),
    )
    items, total = await service.get_admin_feed(
        page=page,
        page_size=page_size,
        start_date=start_date,
        end_date=end_date,
        user_id=user_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        search=search,
    )
    sessions = await service.get_work_sessions(
        start_date=start_date,
        end_date=end_date,
        user_id=user_id,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    return AdminAuditEntityDetail(
        summary=entity_summary,
        feed=AdminAuditFeedResponse(
            items=[AdminAuditFeedItem(**item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
            pages=calculate_pages(total, page_size),
        ),
        sessions=[WorkSessionResponse(**session) for session in sessions],
    )
