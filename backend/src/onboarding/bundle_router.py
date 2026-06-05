"""Staff routes for onboarding template bundles ("saved packets", §4.4/4.6).

Thin routes over ``BundleService``. The library is GLOBAL (team-shared, §4.8):
reads gate ``contacts.read``, writes gate ``contacts.create``/``update`` — the
same contacts-permission convention the template + selection routers use (there
is no first-class onboarding permission). Service errors map via
``packet_errors_mapped`` (PacketValidationError → 422, PacketNotFoundError →
404), so a bad request is never a raw 500.
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from src.auth.models import User
from src.core.constants import HTTPStatus
from src.core.permissions import require_permission
from src.core.router_utils import DBSession
from src.onboarding.bundle_schemas import (
    BundleAddItem,
    BundleCreate,
    BundleDetail,
    BundleMember,
    BundleReorder,
    BundleSummary,
    BundleUpdate,
)
from src.onboarding.bundle_service import (
    BundleMemberView,
    BundleService,
    BundleSummaryView,
)
from src.onboarding.models import OnboardingTemplateBundle
from src.onboarding.validation import packet_errors_mapped

router = APIRouter(prefix="/api/onboarding", tags=["onboarding-bundles"])

ReadUser = Annotated[User, Depends(require_permission("contacts", "read"))]
CreateUser = Annotated[User, Depends(require_permission("contacts", "create"))]
UpdateUser = Annotated[User, Depends(require_permission("contacts", "update"))]


def _to_detail(
    bundle: OnboardingTemplateBundle,
    members: list[BundleMemberView],
    send_ready: bool,
) -> BundleDetail:
    return BundleDetail(
        id=bundle.id,
        name=bundle.name,
        description=bundle.description,
        is_active=bundle.is_active,
        item_count=len(members),
        send_ready=send_ready,
        created_at=bundle.created_at,
        updated_at=bundle.updated_at,
        members=[BundleMember.model_validate(m) for m in members],
    )


@router.post(
    "/template-bundles",
    response_model=BundleDetail,
    status_code=HTTPStatus.CREATED,
)
async def create_bundle(
    data: BundleCreate,
    current_user: CreateUser,
    db: DBSession,
):
    """Create a saved packet from the wizard (mint a template per item +
    record the ordered bundle, atomically)."""
    service = BundleService(db)
    with packet_errors_mapped():
        bundle = await service.create_from_wizard(
            current_user=current_user,
            name=data.name,
            description=data.description,
            items=data.items,
        )
    _bundle, members, send_ready = await service.get_bundle_detail(bundle.id)
    return _to_detail(bundle, members, send_ready)


@router.get("/template-bundles", response_model=list[BundleSummary])
async def list_bundles(
    current_user: ReadUser,
    db: DBSession,
    include_inactive: bool = False,
):
    """Global team library of saved packets (retired ones via include_inactive)."""
    summaries: list[BundleSummaryView] = await BundleService(db).list_bundles(
        include_inactive=include_inactive
    )
    return [BundleSummary.model_validate(s) for s in summaries]


@router.get("/template-bundles/{bundle_id}", response_model=BundleDetail)
async def get_bundle(
    bundle_id: int,
    current_user: ReadUser,
    db: DBSession,
):
    """One saved packet with its ordered members + per-member send-readiness."""
    with packet_errors_mapped():
        bundle, members, send_ready = await BundleService(db).get_bundle_detail(
            bundle_id
        )
    return _to_detail(bundle, members, send_ready)


@router.patch("/template-bundles/{bundle_id}", response_model=BundleDetail)
async def update_bundle(
    bundle_id: int,
    data: BundleUpdate,
    current_user: UpdateUser,
    db: DBSession,
):
    """Rename / re-describe / retire-restore a saved packet."""
    service = BundleService(db)
    with packet_errors_mapped():
        await service.update_bundle(
            bundle_id,
            current_user=current_user,
            **data.model_dump(exclude_unset=True),
        )
        bundle, members, send_ready = await service.get_bundle_detail(bundle_id)
    return _to_detail(bundle, members, send_ready)


@router.post("/template-bundles/{bundle_id}/reorder", response_model=BundleDetail)
async def reorder_bundle(
    bundle_id: int,
    data: BundleReorder,
    current_user: UpdateUser,
    db: DBSession,
):
    """Reorder a saved packet's members by a permutation of their item ids."""
    with packet_errors_mapped():
        bundle, members, send_ready = await BundleService(db).reorder(
            bundle_id,
            ordered_item_ids=data.ordered_item_ids,
            current_user=current_user,
        )
    return _to_detail(bundle, members, send_ready)


@router.post("/template-bundles/{bundle_id}/items", response_model=BundleDetail)
async def add_bundle_item(
    bundle_id: int,
    data: BundleAddItem,
    current_user: UpdateUser,
    db: DBSession,
):
    """Append an existing template to a saved packet."""
    with packet_errors_mapped():
        bundle, members, send_ready = await BundleService(db).add_item(
            bundle_id, template_id=data.template_id, current_user=current_user
        )
    return _to_detail(bundle, members, send_ready)


@router.delete(
    "/template-bundles/{bundle_id}/items/{item_id}",
    status_code=HTTPStatus.NO_CONTENT,
)
async def remove_bundle_item(
    bundle_id: int,
    item_id: int,
    current_user: UpdateUser,
    db: DBSession,
):
    """Remove one member (refuses to remove the last one — §C3)."""
    with packet_errors_mapped():
        await BundleService(db).remove_item(
            bundle_id, item_id, current_user=current_user
        )


@router.delete(
    "/template-bundles/{bundle_id}", status_code=HTTPStatus.NO_CONTENT
)
async def delete_bundle(
    bundle_id: int,
    current_user: UpdateUser,
    db: DBSession,
):
    """Hard-delete a saved packet (its items CASCADE on Postgres; the minted
    templates are NOT touched)."""
    with packet_errors_mapped():
        await BundleService(db).delete_bundle(bundle_id)
