"""Attachment API routes for file upload, download, listing, and deletion."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, RedirectResponse

from src.attachments.schemas import AttachmentListResponse, AttachmentResponse
from src.attachments.service import AttachmentService
from src.core.constants import HTTPStatus
from src.core.data_scope import DataScope, get_data_scope
from src.core.entity_access import require_entity_access
from src.core.router_utils import CurrentUser, DBSession, raise_bad_request, raise_not_found

router = APIRouter(prefix="/api/attachments", tags=["attachments"])
logger = logging.getLogger(__name__)


@router.post("/upload", response_model=AttachmentResponse, status_code=HTTPStatus.CREATED)
async def upload_file(
    current_user: CurrentUser,
    db: DBSession,
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
    file: UploadFile = File(...),
    entity_type: str = Form(...),
    entity_id: int = Form(...),
    category: str | None = Form(None),
):
    """Upload a file attachment for an entity."""
    # ``contracts`` retired 2026-05-14 — dropped to prevent a stale
    # browser tab from POSTing uploads that create orphan attachment
    # rows pointing at a Contract whose detail page no longer exists.
    # ``opportunities`` left intact pending a separate cleanup pass
    # (PR1 frontend rip removed the detail page but historical rows
    # may still need backend-only attachment reads).
    valid_entity_types = {
        "contacts", "companies", "leads", "opportunities",
        "expenses", "proposals", "payments",
    }
    if entity_type not in valid_entity_types:
        raise_bad_request(f"Invalid entity_type. Must be one of: {', '.join(sorted(valid_entity_types))}")

    await require_entity_access(db, entity_type, entity_id, current_user, data_scope)

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
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
    as_json: bool = Query(False, alias="as_json"),
):
    """Download an attachment file.

    Default behavior is a 307 redirect to a short-lived R2 presigned URL
    (or a FileResponse when object storage isn't configured). The browser
    follows the redirect as a top-level navigation when the frontend uses
    ``window.open`` on this URL, so no CORS preflight is needed.

    XHR-based fetch flows (the staff preview path) must pass
    ``?as_json=1`` to receive ``{"download_url": "..."}`` instead. axios
    cannot intercept a cross-origin redirect — the browser auto-follows it
    and R2 doesn't return CORS headers, so the redirect path 502s in the
    browser console even though the underlying request would have worked
    via navigation.
    """
    service = AttachmentService(db)
    attachment = await service.get_attachment(attachment_id)
    if not attachment:
        raise_not_found("Attachment", attachment_id)

    await require_entity_access(
        db, attachment.entity_type, attachment.entity_id, current_user, data_scope,
    )

    try:
        download_url = await service.get_download_url(attachment)
    except Exception:
        # logger.exception so Sentry / log aggregator see the stack — R2
        # outages, expired creds, or unexpected boto3 errors otherwise
        # collapse to a generic "File not found" on the fallback path and
        # the real cause stays invisible. Local-disk fallback still runs
        # below for dev/test where R2 isn't configured.
        logger.exception(
            "Failed to get presigned download URL for attachment %s",
            attachment_id,
        )
        download_url = None

    if download_url:
        if as_json:
            return {"download_url": download_url}
        return RedirectResponse(url=download_url, status_code=307)

    # No presigned URL available (object storage not configured, or presign
    # failed). The JSON path cannot serve binary bytes — the frontend
    # expects {"download_url": "..."} and silently gets undefined when it
    # receives raw PDF content, surfacing the misleading "Preview
    # unavailable" toast. Always 503 on the JSON path so the error is
    # explicit regardless of whether a local disk copy exists.
    if as_json:
        raise HTTPException(
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            detail="Attachment storage temporarily unavailable",
        )

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
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
    category: str | None = Query(None),
):
    """List all attachments for a given entity, optionally filtered by category."""
    await require_entity_access(db, entity_type, entity_id, current_user, data_scope)

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
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
):
    """Delete an attachment."""
    service = AttachmentService(db)
    attachment = await service.get_attachment(attachment_id)
    if not attachment:
        raise_not_found("Attachment", attachment_id)

    await require_entity_access(
        db, attachment.entity_type, attachment.entity_id, current_user, data_scope,
    )

    await service.delete_attachment(attachment)
