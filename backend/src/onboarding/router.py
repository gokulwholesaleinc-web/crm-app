"""Onboarding template API routes (build-order §C).

Phase 1 = template library CRUD only (no packets / public routes / e-sign).
Writes gate on ``check_ownership``; reads are global (team library, §5.1).
``FieldDefinitionError`` → 422 via a small context manager (NOT
``value_error_as_400`` which would yield 400, build-order §G #2).
"""

import logging
from contextlib import contextmanager
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response

from src.auth.models import User
from src.core.constants import HTTPStatus
from src.core.http_errors import value_error_as_400
from src.core.permissions import require_permission
from src.core.router_utils import CurrentUser, DBSession, check_ownership, raise_not_found
from src.onboarding.schemas import (
    TemplateCreate,
    TemplateResponse,
    TemplateUpdate,
)
from src.onboarding.service import FieldDefinitionError, OnboardingTemplateService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])

# No first-class "onboarding" permission domain — staff onboarding writes are
# customer-facing, so reuse contacts write perms (mirrors proposals router).
OnbCreateUser = Annotated[User, Depends(require_permission("contacts", "create"))]
OnbUpdateUser = Annotated[User, Depends(require_permission("contacts", "update"))]

# 25 MB cap on uploaded onboarding PDFs (matches the proposals signing-doc cap).
_MAX_PDF_BYTES = 25 * 1024 * 1024


@contextmanager
def _field_definition_error_as_422():
    """Map a service-raised ``FieldDefinitionError`` to HTTP 422."""
    try:
        yield
    except FieldDefinitionError as exc:
        logger.warning("Onboarding field_definitions validation 422: %s", exc)
        raise HTTPException(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


async def _get_template_or_404(service: OnboardingTemplateService, template_id: int):
    template = await service.get(template_id)
    if template is None:
        raise_not_found("Onboarding template", template_id)
    return template


@router.post(
    "/templates",
    response_model=TemplateResponse,
    status_code=HTTPStatus.CREATED,
)
async def create_template(
    data: TemplateCreate,
    current_user: OnbCreateUser,
    db: DBSession,
):
    """Create the template metadata row (PDF + fields come later)."""
    service = OnboardingTemplateService(db)
    template = await service.create(current_user=current_user, **data.model_dump())
    return TemplateResponse.model_validate(template)


@router.get("/templates", response_model=list[TemplateResponse])
async def list_templates(
    current_user: CurrentUser,
    db: DBSession,
    service_tag: str | None = Query(default=None),
    include_inactive: bool = Query(default=False),
):
    """Global team library — every template, no owner filter (§5.1)."""
    service = OnboardingTemplateService(db)
    templates = await service.list(
        service_tag=service_tag, include_inactive=include_inactive
    )
    return [TemplateResponse.model_validate(t) for t in templates]


@router.get("/templates/{template_id}", response_model=TemplateResponse)
async def get_template(
    template_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    service = OnboardingTemplateService(db)
    template = await _get_template_or_404(service, template_id)
    return TemplateResponse.model_validate(template)


@router.patch("/templates/{template_id}", response_model=TemplateResponse)
async def update_template(
    template_id: int,
    data: TemplateUpdate,
    current_user: OnbUpdateUser,
    db: DBSession,
):
    """Update metadata and/or field_definitions (422 on field validation)."""
    service = OnboardingTemplateService(db)
    template = await _get_template_or_404(service, template_id)
    check_ownership(template, current_user, "onboarding template")
    with _field_definition_error_as_422():
        template = await service.update(
            template,
            current_user=current_user,
            **data.model_dump(exclude_unset=True),
        )
    return TemplateResponse.model_validate(template)


@router.post("/templates/{template_id}/pdf", response_model=TemplateResponse)
async def upload_template_pdf(
    template_id: int,
    current_user: OnbUpdateUser,
    db: DBSession,
    file: UploadFile = File(...),
):
    """Upload (or re-upload) the template PDF. Re-upload clears fields."""
    service = OnboardingTemplateService(db)
    template = await _get_template_or_404(service, template_id)
    check_ownership(template, current_user, "onboarding template")
    if file.size is None:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="PDF upload size is required (chunked uploads not supported).",
        )
    if file.size > _MAX_PDF_BYTES:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="PDF exceeds 25 MB limit.",
        )
    content = await file.read()
    with value_error_as_400():
        template = await service.upload_pdf(
            template, current_user=current_user, content=content
        )
    return TemplateResponse.model_validate(template)


@router.get("/templates/{template_id}/pdf")
async def get_template_pdf(
    template_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Stream the stored template PDF bytes."""
    service = OnboardingTemplateService(db)
    template = await _get_template_or_404(service, template_id)
    try:
        content = await service.get_pdf_bytes(template)
    except FileNotFoundError:
        raise_not_found("Onboarding template PDF", template_id)
    except RuntimeError as exc:
        # R2 creds missing / storage backend unavailable.
        raise HTTPException(
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            detail="PDF storage is unavailable.",
        ) from exc
    return Response(content=content, media_type="application/pdf")


@router.post("/templates/{template_id}/retire", response_model=TemplateResponse)
async def retire_template(
    template_id: int,
    current_user: OnbUpdateUser,
    db: DBSession,
):
    """Soft-retire a template (is_active=False)."""
    service = OnboardingTemplateService(db)
    template = await _get_template_or_404(service, template_id)
    check_ownership(template, current_user, "onboarding template")
    template = await service.retire(template, current_user=current_user)
    return TemplateResponse.model_validate(template)
