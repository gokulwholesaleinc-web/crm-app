"""Onboarding template API routes (build-order §C).

Phase 1 = template library CRUD only (no packets / public routes / e-sign).
Writes gate on ``check_ownership``; reads gate on contacts.read but stay
global (team library, §5.1). Service errors map via context managers below:
FieldDefinitionError → 422, Stale/Retired → 409, PdfRejected → 400,
StorageWrite → 503 (NOT ``value_error_as_400`` blanket-400, build-order §G #2).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response

from src.auth.models import User
from src.core.constants import HTTPStatus
from src.core.permissions import require_permission
from src.core.router_utils import DBSession, check_ownership, raise_not_found
from src.onboarding.schemas import (
    StarterResponse,
    TemplateCloneRequest,
    TemplateCreate,
    TemplateFromStarterRequest,
    TemplateResponse,
    TemplateUpdate,
)
from src.onboarding.service import OnboardingTemplateService
from src.onboarding.starter_definitions import get_starter, onboarding_template_specs
from src.onboarding.validation import (
    field_definition_error_as_422,
    upload_errors_mapped,
)

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])

# No "onboarding" permission domain — reuse contacts perms (mirrors proposals).
# Reads gate on contacts.read (#3): still GLOBAL across owners, not bare-auth.
OnbReadUser = Annotated[User, Depends(require_permission("contacts", "read"))]
OnbCreateUser = Annotated[User, Depends(require_permission("contacts", "create"))]
OnbUpdateUser = Annotated[User, Depends(require_permission("contacts", "update"))]

# 25 MB cap on uploaded onboarding PDFs (matches the proposals signing-doc cap).
_MAX_PDF_BYTES = 25 * 1024 * 1024


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
    # DuplicateTemplateNameError → 422 (S1): a same-name collision is a clean
    # client error, never a raw 500 from the unique-constraint violation.
    with field_definition_error_as_422():
        template = await service.create(current_user=current_user, **data.model_dump())
    return TemplateResponse.from_template(template)


@router.get("/templates", response_model=list[TemplateResponse])
async def list_templates(
    current_user: OnbReadUser,
    db: DBSession,
    service_tag: str | None = Query(default=None),
    include_inactive: bool = Query(default=False),
):
    """Global team library — every template, no owner filter (§5.1, #3 read-gated)."""
    service = OnboardingTemplateService(db)
    templates = await service.list(
        service_tag=service_tag, include_inactive=include_inactive
    )
    return [TemplateResponse.from_template(t) for t in templates]


@router.get("/templates/starters", response_model=list[StarterResponse])
async def list_starters(current_user: OnbReadUser):
    """List the built-in starter templates (read-gated).

    Declared BEFORE ``/templates/{template_id}`` so the literal ``starters`` path
    isn't swallowed by the int path param. The wizard offers these first; the
    from-starter route clones one by ``key``.
    """
    return [
        StarterResponse(
            key=s["key"],
            name=s["name"],
            description=s["description"],
            kind=s["kind"],
            service_tag=s["service_tag"],
        )
        for s in onboarding_template_specs()
    ]


@router.get("/templates/{template_id}", response_model=TemplateResponse)
async def get_template(
    template_id: int,
    current_user: OnbReadUser,
    db: DBSession,
):
    service = OnboardingTemplateService(db)
    template = await _get_template_or_404(service, template_id)
    return TemplateResponse.from_template(template)


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
    with field_definition_error_as_422():
        template = await service.update(
            template,
            current_user=current_user,
            **data.model_dump(exclude_unset=True),
        )
    return TemplateResponse.from_template(template)


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
    with upload_errors_mapped():
        template = await service.upload_pdf(
            template, current_user=current_user, content=content
        )
    return TemplateResponse.from_template(template)


@router.get("/templates/{template_id}/pdf")
async def get_template_pdf(
    template_id: int,
    current_user: OnbReadUser,
    db: DBSession,
):
    """Stream the stored template PDF bytes (read-gated on contacts.read)."""
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


@router.post(
    "/templates/from-starter",
    response_model=TemplateResponse,
    status_code=HTTPStatus.CREATED,
)
async def create_template_from_starter(
    data: TemplateFromStarterRequest,
    current_user: OnbCreateUser,
    db: DBSession,
):
    """Instantiate a built-in starter into a fresh team-library template.

    Unknown ``starter_key`` → 404. Explicit ``name`` collision → 422; omitted →
    auto-suffix off the starter name.
    """
    spec = get_starter(data.starter_key)
    if spec is None:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail=f"Unknown onboarding starter '{data.starter_key}'.",
        )
    service = OnboardingTemplateService(db)
    with field_definition_error_as_422():
        template = await service.create_from_starter(
            spec, current_user=current_user, name=data.name
        )
    return TemplateResponse.from_template(template)


@router.post(
    "/templates/{template_id}/clone",
    response_model=TemplateResponse,
    status_code=HTTPStatus.CREATED,
)
async def clone_template(
    template_id: int,
    data: TemplateCloneRequest,
    current_user: OnbCreateUser,
    db: DBSession,
):
    """Clone an active questionnaire/upload template into a fresh one.

    Missing source → 404; e-sign or retired source → 422; explicit ``name``
    collision → 422; omitted ``name`` → auto-suffix ``"{source} (copy[, N])"``.
    """
    service = OnboardingTemplateService(db)
    source = await _get_template_or_404(service, template_id)
    with field_definition_error_as_422():
        template = await service.clone_template(
            source, current_user=current_user, name=data.name
        )
    return TemplateResponse.from_template(template)


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
    return TemplateResponse.from_template(template)


@router.post("/templates/{template_id}/restore", response_model=TemplateResponse)
async def restore_template(
    template_id: int,
    current_user: OnbUpdateUser,
    db: DBSession,
):
    """Restore a retired template (is_active=True) so it can be edited again."""
    service = OnboardingTemplateService(db)
    template = await _get_template_or_404(service, template_id)
    check_ownership(template, current_user, "onboarding template")
    template = await service.restore(template, current_user=current_user)
    return TemplateResponse.from_template(template)
