"""Attachment API routes for file upload, download, listing, and deletion."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import select

from src.attachments.models import Attachment
from src.attachments.schemas import AttachmentListResponse, AttachmentResponse
from src.attachments.service import INLINE_SAFE_MIME_TYPES, AttachmentService
from src.core.constants import HTTPStatus
from src.core.data_scope import DataScope, get_data_scope
from src.core.entity_access import require_entity_access
from src.core.router_utils import CurrentUser, DBSession, raise_bad_request, raise_not_found

router = APIRouter(prefix="/api/attachments", tags=["attachments"])
logger = logging.getLogger(__name__)

# Attachments holding sensitive onboarding uploads (gov-ID etc.) are NOT served
# under the broad contact-access rule — only the contact's OWNER or an admin may
# read them (§D.4 decision #3). Hardened-download headers (defense against
# content-sniffing / inline render of a renamed payload) are applied to EVERY
# attachment download regardless of category.
SENSITIVE_ONBOARDING_CATEGORY = "onboarding_sensitive"


async def _may_read_sensitive(
    db: DBSession, entity_type: str, entity_id: int, data_scope: DataScope
) -> bool:
    """True iff the caller may read a sensitive onboarding attachment on this
    entity: an admin/manager (``can_see_all``) OR the OWNER of the parent
    contact. Sensitive onboarding uploads only ever live on ``contacts``."""
    if data_scope.can_see_all():
        return True
    if entity_type != "contacts":
        return True
    from src.contacts.models import Contact

    contact_owner = (
        await db.execute(
            select(Contact.owner_id).where(Contact.id == entity_id)
        )
    ).scalar_one_or_none()
    return contact_owner is not None and contact_owner == data_scope.user_id


async def _assert_sensitive_read_allowed(
    db: DBSession, attachment: Attachment, data_scope: DataScope
) -> None:
    """Owner-or-admin gate for a sensitive onboarding attachment (§D.4).

    The generic ``require_entity_access`` already ran (contact access). For a
    ``onboarding_sensitive`` attachment that is NOT enough — a shared-list or
    manager-bypass reader must still be refused unless owner/admin. Applied to
    READ (download) AND DELETE (a low-priv reader must not destroy a submitted
    gov-ID). Non-sensitive attachments skip this entirely.
    """
    if attachment.category != SENSITIVE_ONBOARDING_CATEGORY:
        return
    if not await _may_read_sensitive(
        db, attachment.entity_type, attachment.entity_id, data_scope
    ):
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN,
            detail="Only the contact owner or an admin may access this file.",
        )


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
    inline: bool = Query(False, alias="inline"),
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

    ``?inline=1`` (the "View" action) serves the file with an INLINE
    disposition so the browser renders it in a tab — but ONLY for a vetted
    content type (PDF / raster image); any other type ignores the flag and
    is still forced as an ``attachment`` download (anti-sniff, §D.4 / PF3).
    """
    service = AttachmentService(db)
    attachment = await service.get_attachment(attachment_id)
    if not attachment:
        raise_not_found("Attachment", attachment_id)

    await require_entity_access(
        db, attachment.entity_type, attachment.entity_id, current_user, data_scope,
    )
    # Sensitive onboarding uploads (gov-ID) are owner-or-admin only — a narrow
    # ELEVATION on top of the contact-access check above (§D.4).
    await _assert_sensitive_read_allowed(db, attachment, data_scope)

    # Honour inline only for the safe allowlist — a renamed HTML/SVG payload
    # must never be coaxed into an inline render via this flag.
    inline_ok = inline and attachment.mime_type in INLINE_SAFE_MIME_TYPES

    try:
        download_url = await service.get_download_url(attachment, inline=inline_ok)
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

    # nosniff is ALWAYS set so a mislabeled payload can't be content-sniffed into
    # active content. Disposition defaults to ``attachment`` (forced download);
    # only an allowlisted safe type requested with ``inline=1`` renders in-tab —
    # the same gate the presigned-URL branch applies (§D.4).
    return FileResponse(
        path=str(file_path),
        filename=attachment.original_filename,
        media_type=attachment.mime_type,
        content_disposition_type="inline" if inline_ok else "attachment",
        headers={"X-Content-Type-Options": "nosniff"},
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
    # Hide sensitive onboarding uploads (gov-ID) from non-owner/admin readers —
    # even their metadata (filename / category) is PII (sec).
    if not await _may_read_sensitive(db, entity_type, entity_id, data_scope):
        items = [a for a in items if a.category != SENSITIVE_ONBOARDING_CATEGORY]
        total = len(items)
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
    # A sensitive onboarding upload (gov-ID) may only be DELETED by the contact
    # owner or an admin — a shared-list reader must not destroy submitted PII /
    # the attachment the onboarding packet references (sec).
    await _assert_sensitive_read_allowed(db, attachment, data_scope)

    await service.delete_attachment(attachment)
