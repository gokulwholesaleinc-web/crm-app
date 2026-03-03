"""Attachment API routes for file upload, download, listing, and deletion."""

from typing import Optional
from fastapi import APIRouter, UploadFile, File, Form, Query
from fastapi.responses import FileResponse, RedirectResponse

from src.core.constants import HTTPStatus, EntityNames
from src.core.router_utils import DBSession, CurrentUser, raise_not_found, raise_bad_request
from src.attachments.schemas import AttachmentResponse, AttachmentListResponse
from src.attachments.service import AttachmentService

router = APIRouter(prefix="/api/attachments", tags=["attachments"])


@router.post("/upload", response_model=AttachmentResponse, status_code=HTTPStatus.CREATED)
async def upload_file(
    current_user: CurrentUser,
    db: DBSession,
    file: UploadFile = File(...),
    entity_type: str = Form(...),
    entity_id: int = Form(...),
    category: Optional[str] = Form(None),
):
    """Upload a file attachment for an entity."""
    valid_entity_types = {"contacts", "companies", "leads", "opportunities", "expenses"}
    if entity_type not in valid_entity_types:
        raise_bad_request(f"Invalid entity_type. Must be one of: {', '.join(sorted(valid_entity_types))}")

    valid_categories = {"document", "contract", "image", "report", "receipt", "invoice", "other"}
    if category and category not in valid_categories:
        raise_bad_request(f"Invalid category. Must be one of: {', '.join(sorted(valid_categories))}")

    service = AttachmentService(db)
    try:
        attachment = await service.upload_file(
            file=file,
            entity_type=entity_type,
            entity_id=entity_id,
            user_id=current_user.id,
            category=category,
        )
    except ValueError as e:
        raise_bad_request(str(e))

    return AttachmentResponse.model_validate(attachment)


@router.get("/{attachment_id}/download")
async def download_attachment(
    attachment_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Download an attachment file."""
    service = AttachmentService(db)
    attachment = await service.get_attachment(attachment_id)
    if not attachment:
        raise_not_found(EntityNames.NOTE, attachment_id)

    download_url = await service.get_download_url(attachment)
    if download_url:
        return RedirectResponse(url=download_url, status_code=307)

    file_path = service.get_file_path(attachment)
    if not file_path or not file_path.exists():
        raise_not_found("File", attachment_id)

    return FileResponse(
        path=str(file_path),
        filename=attachment.original_filename,
        media_type=attachment.mime_type,
    )


@router.get("/{entity_type}/{entity_id}", response_model=AttachmentListResponse)
async def list_attachments(
    entity_type: str,
    entity_id: int,
    current_user: CurrentUser,
    db: DBSession,
    category: Optional[str] = Query(None),
):
    """List all attachments for a given entity, optionally filtered by category."""
    service = AttachmentService(db)
    items, total = await service.list_attachments(entity_type, entity_id, category=category)
    return AttachmentListResponse(
        items=[AttachmentResponse.model_validate(a) for a in items],
        total=total,
    )


@router.delete("/{attachment_id}", status_code=HTTPStatus.NO_CONTENT)
async def delete_attachment(
    attachment_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Delete an attachment."""
    service = AttachmentService(db)
    attachment = await service.get_attachment(attachment_id)
    if not attachment:
        raise_not_found("Attachment", attachment_id)

    await service.delete_attachment(attachment)
