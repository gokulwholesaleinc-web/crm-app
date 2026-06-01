"""Staff routes for a proposal's onboarding-template selections (Phase 3, §A).

Thin routes over ``SelectionService``. Every route gates on the *proposal*
via ``require_entity_access(db, "proposals", ...)`` (data-scope) so a rep can't
curate another owner's proposal. Reads gate ``contacts.read``; mutations gate
``contacts.update`` — the same proposal-as-contacts-write convention used by
``proposals/router.py`` (there is no first-class ``proposals`` permission).
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from src.auth.models import User
from src.core.data_scope import DataScope, get_data_scope
from src.core.entity_access import require_entity_access
from src.core.permissions import require_permission
from src.core.router_utils import DBSession
from src.onboarding.packet_schemas import (
    SelectionReorder,
    SelectionResponse,
    SelectionSet,
)
from src.onboarding.selection_service import SelectionService
from src.onboarding.validation import packet_errors_mapped

router = APIRouter(prefix="/api/onboarding", tags=["onboarding-selections"])

ReadUser = Annotated[User, Depends(require_permission("contacts", "read"))]
UpdateUser = Annotated[User, Depends(require_permission("contacts", "update"))]
Scope = Annotated[DataScope, Depends(get_data_scope)]


@router.get(
    "/proposals/{proposal_id}/selections",
    response_model=list[SelectionResponse],
)
async def list_selections(
    proposal_id: int,
    current_user: ReadUser,
    db: DBSession,
    data_scope: Scope,
):
    """List a proposal's onboarding-template selections (ordered)."""
    await require_entity_access(
        db, "proposals", proposal_id, current_user, data_scope
    )
    selections = await SelectionService(db).list_selections(proposal_id)
    return [SelectionResponse.model_validate(s) for s in selections]


@router.put(
    "/proposals/{proposal_id}/selections",
    response_model=list[SelectionResponse],
)
async def set_selections(
    proposal_id: int,
    data: SelectionSet,
    current_user: UpdateUser,
    db: DBSession,
    data_scope: Scope,
):
    """Replace the full ordered selection list (422 on retired/missing)."""
    await require_entity_access(
        db, "proposals", proposal_id, current_user, data_scope
    )
    with packet_errors_mapped():
        selections = await SelectionService(db).set_selections(
            proposal_id,
            template_ids=data.template_ids,
            actor_id=current_user.id,
        )
    return [SelectionResponse.model_validate(s) for s in selections]


@router.post(
    "/proposals/{proposal_id}/selections/reorder",
    response_model=list[SelectionResponse],
)
async def reorder_selections(
    proposal_id: int,
    data: SelectionReorder,
    current_user: UpdateUser,
    db: DBSession,
    data_scope: Scope,
):
    """Reorder the selections by a permutation of their ids."""
    await require_entity_access(
        db, "proposals", proposal_id, current_user, data_scope
    )
    with packet_errors_mapped():
        selections = await SelectionService(db).reorder(
            proposal_id,
            ordered_ids=data.ordered_ids,
            actor_id=current_user.id,
        )
    return [SelectionResponse.model_validate(s) for s in selections]


@router.delete(
    "/proposals/{proposal_id}/selections/{selection_id}",
    status_code=204,
)
async def remove_selection(
    proposal_id: int,
    selection_id: int,
    current_user: UpdateUser,
    db: DBSession,
    data_scope: Scope,
):
    """Remove one onboarding-template selection from the proposal."""
    await require_entity_access(
        db, "proposals", proposal_id, current_user, data_scope
    )
    with packet_errors_mapped():
        await SelectionService(db).remove(proposal_id, selection_id)
