"""Duplicate detection and merge API routes."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from src.auth.models import User
from src.core.http_errors import value_error_as_400
from src.core.permissions import require_manager_or_above
from src.core.router_utils import CurrentUser, DBSession, raise_bad_request
from src.dedup.service import (
    ALLOWED_CLUSTER_ENTITIES,
    ALLOWED_CLUSTER_KEYS_BY_ENTITY,
    DedupService,
)

router = APIRouter(prefix="/api/dedup", tags=["dedup"])


class DedupCheckRequest(BaseModel):
    entity_type: str
    data: dict[str, Any]


class DedupCheckResponse(BaseModel):
    duplicates: list[dict[str, Any]]
    has_duplicates: bool


class MergeRequest(BaseModel):
    entity_type: str
    primary_id: int
    secondary_id: int


class MergeResponse(BaseModel):
    success: bool
    primary_id: int
    message: str


@router.post("/check", response_model=DedupCheckResponse)
async def check_duplicates(
    request: DedupCheckRequest,
    current_user: CurrentUser,
    db: DBSession,
):
    """Check for potential duplicates before creating an entity."""
    valid_types = {"contacts", "companies", "leads"}
    if request.entity_type not in valid_types:
        raise_bad_request(f"Invalid entity_type. Must be one of: {', '.join(sorted(valid_types))}")

    service = DedupService(db)
    duplicates = await service.check_duplicates(request.entity_type, request.data)

    return DedupCheckResponse(
        duplicates=duplicates,
        has_duplicates=len(duplicates) > 0,
    )


@router.post("/merge", response_model=MergeResponse)
async def merge_entities(
    request: MergeRequest,
    current_user: Annotated[User, Depends(require_manager_or_above)],
    db: DBSession,
):
    """Merge two records of the same entity type. Secondary is merged into primary."""
    if request.primary_id == request.secondary_id:
        raise_bad_request("Primary and secondary IDs must be different")

    service = DedupService(db)

    with value_error_as_400():
        if request.entity_type == "contacts":
            await service.merge_contacts(request.primary_id, request.secondary_id)
        elif request.entity_type == "companies":
            await service.merge_companies(request.primary_id, request.secondary_id)
        elif request.entity_type == "leads":
            await service.merge_leads(request.primary_id, request.secondary_id)
        else:
            raise_bad_request(f"Invalid entity_type: {request.entity_type}")

    return MergeResponse(
        success=True,
        primary_id=request.primary_id,
        message=f"Successfully merged {request.entity_type} {request.secondary_id} into {request.primary_id}",
    )


# ----------------------------------------------------------------------
# Admin: cluster browser
# ----------------------------------------------------------------------


class ClustersResponse(BaseModel):
    entity_type: str
    key: str
    clusters: list[dict[str, Any]]
    skipped_no_key: int


class MergeClusterRequest(BaseModel):
    entity_type: str
    winner_id: int
    loser_ids: list[int] = Field(..., min_length=1)


class MergeClusterResponse(BaseModel):
    success: bool
    winner_id: int
    merged_ids: list[int]
    failures: list[dict[str, Any]]


@router.get("/clusters", response_model=ClustersResponse)
async def list_duplicate_clusters(
    current_user: Annotated[User, Depends(require_manager_or_above)],
    db: DBSession,
    entity_type: str = Query("contacts"),
    key: str = Query("email"),
):
    """Return every cluster of 2+ live records that share a match key.

    Manager+ only — this surfaces every contact in the system in a single
    page so it carries the same trust level as bulk update/delete.
    """
    if entity_type not in ALLOWED_CLUSTER_ENTITIES:
        raise_bad_request(
            f"Invalid entity_type '{entity_type}'. Allowed: {', '.join(ALLOWED_CLUSTER_ENTITIES)}"
        )
    allowed_keys = ALLOWED_CLUSTER_KEYS_BY_ENTITY[entity_type]
    if key not in allowed_keys:
        raise_bad_request(
            f"Invalid key '{key}' for {entity_type}. Allowed: {', '.join(allowed_keys)}"
        )

    service = DedupService(db)
    with value_error_as_400():
        result = await service.find_duplicate_clusters(entity_type=entity_type, key=key)

    return ClustersResponse(
        entity_type=entity_type,
        key=key,
        clusters=result["clusters"],
        skipped_no_key=result["skipped_no_key"],
    )


@router.post("/merge-cluster", response_model=MergeClusterResponse)
async def merge_cluster(
    request: MergeClusterRequest,
    current_user: Annotated[User, Depends(require_manager_or_above)],
    db: DBSession,
):
    """Merge every loser_id into winner_id for a single entity type.

    Reuses :meth:`DedupService.merge_contacts` / ``merge_companies`` /
    ``merge_leads`` so FK fanout, audit logging, and soft-delete behavior
    match the single-pair endpoint. Bad ids (already-merged, missing) are
    skipped and reported in ``failures`` — the success path returns the
    list of ids actually merged.
    """
    service = DedupService(db)
    with value_error_as_400():
        result = await service.merge_cluster(
            entity_type=request.entity_type,
            winner_id=request.winner_id,
            loser_ids=request.loser_ids,
            user_id=current_user.id,
        )
    return MergeClusterResponse(
        success=True,
        winner_id=result["winner_id"],
        merged_ids=result["merged_ids"],
        failures=result["failures"],
    )
