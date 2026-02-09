"""Audit log API routes."""

from fastapi import APIRouter, Query
from src.core.router_utils import DBSession, CurrentUser, calculate_pages
from src.audit.schemas import AuditLogListResponse, AuditLogResponse
from src.audit.service import AuditService

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("/{entity_type}/{entity_id}", response_model=AuditLogListResponse)
async def get_entity_audit_log(
    entity_type: str,
    entity_id: int,
    current_user: CurrentUser,
    db: DBSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
):
    """Get audit log for a specific entity."""
    service = AuditService(db)
    items, total = await service.get_entity_log(
        entity_type=entity_type,
        entity_id=entity_id,
        page=page,
        page_size=page_size,
    )
    return AuditLogListResponse(
        items=[AuditLogResponse(**item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
        pages=calculate_pages(total, page_size),
    )
