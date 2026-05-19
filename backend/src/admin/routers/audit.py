"""Admin-only CRM audit dashboard endpoints."""

import csv
import io
import json
import logging
from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)

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

_CSV_COLUMNS = [
    "id",
    "created_at",
    "user_id",
    "user_name",
    "user_email",
    "action",
    "entity_type",
    "entity_id",
    "ip_address",
    "changes",
]


def _stringify_changes(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, default=str, separators=(",", ":"))
    except (TypeError, ValueError):
        return str(value)


def _format_csv_row(row: dict, writer: csv.writer, buffer: io.StringIO) -> str:
    created_at = row.get("created_at")
    if isinstance(created_at, datetime):
        created_at_str = created_at.astimezone(UTC).isoformat()
    else:
        created_at_str = created_at or ""
    writer.writerow([
        row.get("id", ""),
        created_at_str,
        row.get("user_id") or "",
        row.get("user_name") or "",
        row.get("user_email") or "",
        row.get("action", ""),
        row.get("entity_type", ""),
        row.get("entity_id", ""),
        row.get("ip_address") or "",
        _stringify_changes(row.get("changes")),
    ])
    chunk = buffer.getvalue()
    buffer.seek(0)
    buffer.truncate(0)
    return chunk


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


@router.get("/export.csv")
async def export_admin_audit_csv(
    request: Request,
    current_user: CurrentUser,
    db: DBSession,
    start_date: date | None = None,
    end_date: date | None = None,
    user_id: int | None = None,
    entity_type: str | None = None,
    entity_id: int | None = None,
    action: str | None = None,
    search: str | None = None,
):
    """Stream the full filtered audit feed as CSV.

    Unlike the paginated /feed endpoint, this iterates the result set with a
    server-side cursor so a multi-month compliance pull doesn't materialize
    the whole join in memory. Same filters as /feed; no page/page_size.
    """
    _require_admin(current_user)
    service = AuditService(db)

    async def generate():
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(_CSV_COLUMNS)
        yield buffer.getvalue()
        buffer.seek(0)
        buffer.truncate(0)

        # StreamingResponse already flushed 200 OK by the time we hit the
        # cursor. If the DB drops or hits a statement timeout mid-pull,
        # without this guard the user gets a half-complete CSV that opens
        # cleanly in Excel and looks done — auditor reads stale data.
        try:
            async for row in service.iter_admin_feed_rows(
                start_date=start_date,
                end_date=end_date,
                user_id=user_id,
                entity_type=entity_type,
                entity_id=entity_id,
                action=action,
                search=search,
            ):
                yield _format_csv_row(row, writer, buffer)
        except Exception as exc:  # noqa: BLE001 - need to surface any cursor error
            logger.exception("admin audit CSV export failed mid-stream")
            trailer = (
                f"\n# EXPORT TRUNCATED at {datetime.now(UTC).isoformat()} — "
                f"{type(exc).__name__}: retry with a narrower date range or filters.\n"
            )
            yield trailer

    filename = f"crm-audit-{date.today().isoformat()}.csv"
    return StreamingResponse(
        generate(),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
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
