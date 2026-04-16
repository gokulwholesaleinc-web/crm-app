"""Audit log API routes."""

from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from src.core.constants import HTTPStatus
from src.core.data_scope import DataScope, get_data_scope
from src.core.entity_access import _resolve_entity, require_entity_access
from src.core.router_utils import DBSession, CurrentUser, calculate_pages
from src.audit.models import AuditLog
from src.audit.schemas import AuditLogResponse, AuditLogListResponse
from src.audit.service import AuditService

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("/{entity_type}/{entity_id}", response_model=AuditLogListResponse)
async def get_entity_audit_log(
    entity_type: str,
    entity_id: int,
    current_user: CurrentUser,
    db: DBSession,
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """Get audit history for a specific entity.

    Access rules:
    - Admin/manager/superuser: always allowed.
    - Other users: allowed if (a) the parent entity is still accessible
      OR (b) the caller appears as the actor in any audit row for this
      entity — meaning they participated in its history and should be
      able to read it even after delete.
    """
    if not data_scope.can_see_all():
        entity, _ = await _resolve_entity(db, entity_type, entity_id)
        if entity is not None:
            # Live entity — standard access check.
            await require_entity_access(
                db, entity_type, entity_id, current_user, data_scope,
            )
        else:
            # Entity is gone or unknown type — allow only if the caller
            # has at least one audit row for this (entity_type, entity_id).
            result = await db.execute(
                select(AuditLog.id)
                .where(AuditLog.entity_type == entity_type)
                .where(AuditLog.entity_id == entity_id)
                .where(AuditLog.user_id == current_user.id)
                .limit(1)
            )
            if result.scalar_one_or_none() is None:
                raise HTTPException(
                    status_code=HTTPStatus.NOT_FOUND,
                    detail=f"{entity_type} {entity_id} not found",
                )
    service = AuditService(db)
    items, total = await service.get_entity_history(
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
