"""Work session heartbeat API."""

from typing import Annotated

from fastapi import APIRouter, Depends

from src.audit.schemas import WorkSessionHeartbeatRequest, WorkSessionResponse
from src.audit.service import WorkSessionService
from src.core.data_scope import DataScope, get_data_scope
from src.core.entity_access import require_entity_access
from src.core.router_utils import CurrentUser, DBSession

router = APIRouter(prefix="/api/work-sessions", tags=["work-sessions"])


@router.post("/heartbeat", response_model=WorkSessionResponse)
async def record_work_session_heartbeat(
    payload: WorkSessionHeartbeatRequest,
    current_user: CurrentUser,
    db: DBSession,
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
):
    """Record coarse active CRM time for the current user.

    This is intentionally limited to visible/recently-active frontend tabs.
    It tracks entity context and duration only, not keystrokes, screenshots, or
    field-level interaction data.
    """
    await require_entity_access(
        db,
        payload.entity_type,
        payload.entity_id,
        current_user,
        data_scope,
    )
    session = await WorkSessionService(db).heartbeat(
        user_id=current_user.id,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        source=payload.source,
        metadata=payload.metadata,
    )
    return WorkSessionResponse(
        id=session.id,
        user_id=session.user_id,
        user_name=current_user.full_name,
        entity_type=session.entity_type,
        entity_id=session.entity_id,
        started_at=session.started_at,
        last_seen_at=session.last_seen_at,
        ended_at=session.ended_at,
        duration_seconds=session.duration_seconds,
        source=session.source,
        metadata=session.metadata_,
    )
