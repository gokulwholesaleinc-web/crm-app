"""Sales sequence API routes."""

from typing import Optional, List
from fastapi import APIRouter, Query
from src.core.constants import HTTPStatus
from src.core.router_utils import DBSession, CurrentUser, raise_not_found, raise_bad_request
from src.sequences.schemas import (
    SequenceCreate,
    SequenceUpdate,
    SequenceResponse,
    EnrollContactRequest,
    SequenceEnrollmentResponse,
    ProcessDueResult,
)
from src.sequences.service import SequenceService

router = APIRouter(prefix="/api/sequences", tags=["sequences"])


@router.post("", response_model=SequenceResponse, status_code=HTTPStatus.CREATED)
async def create_sequence(
    data: SequenceCreate,
    current_user: CurrentUser,
    db: DBSession,
):
    """Create a new sales sequence."""
    service = SequenceService(db)
    seq = await service.create_sequence(data, current_user.id)
    return SequenceResponse.model_validate(seq)


@router.get("", response_model=List[SequenceResponse])
async def list_sequences(
    current_user: CurrentUser,
    db: DBSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    is_active: Optional[bool] = None,
):
    """List sequences."""
    service = SequenceService(db)
    sequences, _ = await service.get_list(page=page, page_size=page_size, is_active=is_active)
    return [SequenceResponse.model_validate(s) for s in sequences]


@router.get("/{sequence_id}", response_model=SequenceResponse)
async def get_sequence(
    sequence_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Get a sequence by ID."""
    service = SequenceService(db)
    seq = await service.get_by_id(sequence_id)
    if not seq:
        raise_not_found("Sequence", sequence_id)
    return SequenceResponse.model_validate(seq)


@router.put("/{sequence_id}", response_model=SequenceResponse)
async def update_sequence(
    sequence_id: int,
    data: SequenceUpdate,
    current_user: CurrentUser,
    db: DBSession,
):
    """Update a sequence."""
    service = SequenceService(db)
    seq = await service.get_by_id(sequence_id)
    if not seq:
        raise_not_found("Sequence", sequence_id)
    updated = await service.update_sequence(seq, data)
    return SequenceResponse.model_validate(updated)


@router.delete("/{sequence_id}", status_code=HTTPStatus.NO_CONTENT)
async def delete_sequence(
    sequence_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Delete a sequence."""
    service = SequenceService(db)
    seq = await service.get_by_id(sequence_id)
    if not seq:
        raise_not_found("Sequence", sequence_id)
    await service.delete_sequence(seq)


@router.post("/{sequence_id}/enroll", response_model=SequenceEnrollmentResponse)
async def enroll_contact(
    sequence_id: int,
    data: EnrollContactRequest,
    current_user: CurrentUser,
    db: DBSession,
):
    """Enroll a contact in a sequence."""
    service = SequenceService(db)
    seq = await service.get_by_id(sequence_id)
    if not seq:
        raise_not_found("Sequence", sequence_id)
    if not seq.is_active:
        raise_bad_request("Cannot enroll in an inactive sequence")
    enrollment = await service.enroll_contact(sequence_id, data.contact_id)
    return SequenceEnrollmentResponse.model_validate(enrollment)


@router.get("/{sequence_id}/enrollments", response_model=List[SequenceEnrollmentResponse])
async def get_enrollments(
    sequence_id: int,
    current_user: CurrentUser,
    db: DBSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """Get enrollments for a sequence."""
    service = SequenceService(db)
    seq = await service.get_by_id(sequence_id)
    if not seq:
        raise_not_found("Sequence", sequence_id)
    enrollments, _ = await service.get_enrollments(sequence_id, page=page, page_size=page_size)
    return [SequenceEnrollmentResponse.model_validate(e) for e in enrollments]


@router.put("/enrollments/{enrollment_id}/pause", response_model=SequenceEnrollmentResponse)
async def pause_enrollment(
    enrollment_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Pause an active enrollment."""
    service = SequenceService(db)
    enrollment = await service.get_enrollment_by_id(enrollment_id)
    if not enrollment:
        raise_not_found("Enrollment", enrollment_id)
    if enrollment.status != "active":
        raise_bad_request("Can only pause active enrollments")
    updated = await service.pause_enrollment(enrollment_id)
    return SequenceEnrollmentResponse.model_validate(updated)


@router.put("/enrollments/{enrollment_id}/resume", response_model=SequenceEnrollmentResponse)
async def resume_enrollment(
    enrollment_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Resume a paused enrollment."""
    service = SequenceService(db)
    enrollment = await service.get_enrollment_by_id(enrollment_id)
    if not enrollment:
        raise_not_found("Enrollment", enrollment_id)
    if enrollment.status != "paused":
        raise_bad_request("Can only resume paused enrollments")
    updated = await service.resume_enrollment(enrollment_id)
    return SequenceEnrollmentResponse.model_validate(updated)


@router.post("/process-due", response_model=ProcessDueResult)
async def process_due_steps(
    current_user: CurrentUser,
    db: DBSession,
):
    """Process all due enrollment steps."""
    service = SequenceService(db)
    results = await service.process_due_steps()
    return ProcessDueResult(processed=len(results), details=results)


@router.get("/contacts/{contact_id}/enrollments", response_model=List[SequenceEnrollmentResponse])
async def get_contact_enrollments(
    contact_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Get all enrollments for a contact."""
    service = SequenceService(db)
    enrollments = await service.get_contact_enrollments(contact_id)
    return [SequenceEnrollmentResponse.model_validate(e) for e in enrollments]
