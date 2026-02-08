"""Duplicate detection and merge API routes."""

from typing import Dict, Any, List
from pydantic import BaseModel
from fastapi import APIRouter

from src.core.constants import HTTPStatus
from src.core.router_utils import DBSession, CurrentUser, raise_bad_request
from src.dedup.service import DedupService


router = APIRouter(prefix="/api/dedup", tags=["dedup"])


class DedupCheckRequest(BaseModel):
    entity_type: str
    data: Dict[str, Any]


class DedupCheckResponse(BaseModel):
    duplicates: List[Dict[str, Any]]
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
    current_user: CurrentUser,
    db: DBSession,
):
    """Merge two records of the same entity type. Secondary is merged into primary."""
    if request.primary_id == request.secondary_id:
        raise_bad_request("Primary and secondary IDs must be different")

    service = DedupService(db)

    try:
        if request.entity_type == "contacts":
            await service.merge_contacts(request.primary_id, request.secondary_id)
        elif request.entity_type == "companies":
            await service.merge_companies(request.primary_id, request.secondary_id)
        elif request.entity_type == "leads":
            await service.merge_leads(request.primary_id, request.secondary_id)
        else:
            raise_bad_request(f"Invalid entity_type: {request.entity_type}")
    except ValueError as e:
        raise_bad_request(str(e))

    return MergeResponse(
        success=True,
        primary_id=request.primary_id,
        message=f"Successfully merged {request.entity_type} {request.secondary_id} into {request.primary_id}",
    )
