"""Service layer for onboarding templates (build-order §C).

CRUD + PDF upload (with versioning) + save-time field-definition validation.
The library is GLOBAL (team-shared, §5.1) so list/get apply no owner filter;
write paths (upload/patch/retire) gate on ``check_ownership`` in the router.

Field-definition validation raises ``FieldDefinitionError`` which the router
maps to **422**. It deliberately does NOT subclass ``ValueError`` so it can
never be silently downgraded to a 400 by ``value_error_as_400`` (§G #2).
"""

from __future__ import annotations

import io
import math
import uuid

from pypdf import PdfReader
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.onboarding import storage
from src.onboarding.models import OnboardingTemplate

_ALLOWED_PREFILL = {"contact.name", "company.name"}


class FieldDefinitionError(Exception):
    """Save-time field_definitions validation failure → HTTP 422.

    Intentionally NOT a ``ValueError`` so a stray ``value_error_as_400``
    can't silently turn the mandated 422 into a 400.
    """


class OnboardingTemplateService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        *,
        current_user: User,
        name: str,
        description: str | None = None,
        service_tag: str | None = None,
        requires_esign: bool = False,
    ) -> OnboardingTemplate:
        # AuditableMixin does NOT auto-populate created_by_id; set it (and
        # owner_id) explicitly so check_ownership and the audit trail work.
        template = OnboardingTemplate(
            name=name,
            description=description,
            service_tag=service_tag,
            requires_esign=requires_esign,
            owner_id=current_user.id,
            created_by_id=current_user.id,
            field_definitions=[],
        )
        self.db.add(template)
        await self.db.flush()
        await self.db.refresh(template)
        return template

    async def list(
        self,
        *,
        service_tag: str | None = None,
        include_inactive: bool = False,
    ) -> list[OnboardingTemplate]:
        """Global team library — no owner filter (§5.1)."""
        query = select(OnboardingTemplate)
        if service_tag is not None:
            query = query.where(OnboardingTemplate.service_tag == service_tag)
        if not include_inactive:
            query = query.where(OnboardingTemplate.is_active.is_(True))
        query = query.order_by(OnboardingTemplate.created_at.desc())
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get(self, template_id: int) -> OnboardingTemplate | None:
        result = await self.db.execute(
            select(OnboardingTemplate).where(OnboardingTemplate.id == template_id)
        )
        return result.scalar_one_or_none()

    async def update(
        self,
        template: OnboardingTemplate,
        *,
        current_user: User,
        field_definitions: list[dict] | None = None,
        **fields,
    ) -> OnboardingTemplate:
        """Apply a partial update. ``fields`` are already exclude_unset.

        ``field_definitions`` (if provided) is validated against the stored
        PDF and reassigned as a fresh list (JSONB has no in-place mutation
        tracking, but a whole-list reassignment is tracked, §G #7).
        """
        for key, value in fields.items():
            setattr(template, key, value)
        if field_definitions is not None:
            self._validate_field_definitions(
                template, await self._read_pdf_bytes(template), field_definitions
            )
            template.field_definitions = list(field_definitions)
        template.updated_by_id = current_user.id
        await self.db.flush()
        await self.db.refresh(template)
        return template

    async def retire(
        self, template: OnboardingTemplate, *, current_user: User
    ) -> OnboardingTemplate:
        template.is_active = False
        template.updated_by_id = current_user.id
        await self.db.flush()
        await self.db.refresh(template)
        return template

    async def upload_pdf(
        self,
        template: OnboardingTemplate,
        *,
        current_user: User,
        content: bytes,
    ) -> OnboardingTemplate:
        """Store a new PDF for the template.

        A re-upload bumps ``pdf_version``, writes a NEW versioned object
        (the old one is left in place — staff-managed, few templates), and
        CLEARS ``field_definitions`` because the old coords are meaningless
        against a new PDF (build-order §C re-upload semantics).
        """
        if not content:
            raise ValueError("Uploaded PDF is empty")
        # Fail fast on a non-PDF before persisting anything.
        try:
            PdfReader(io.BytesIO(content))
        except Exception as exc:  # pypdf raises a variety of parse errors
            raise ValueError("Uploaded file is not a readable PDF") from exc

        is_reupload = template.pdf_path is not None
        next_version = (template.pdf_version + 1) if is_reupload else template.pdf_version
        # Clean, feature-namespaced key — NOT generate_object_key, whose
        # "uploads/" prefix would double under the storage disk root.
        key = f"onboarding_templates/{template.id}/{uuid.uuid4().hex}.pdf"
        ref = await storage.write(key, content, "application/pdf")

        template.pdf_path = ref
        template.pdf_version = next_version
        if is_reupload:
            template.field_definitions = []
        template.updated_by_id = current_user.id
        await self.db.flush()
        await self.db.refresh(template)
        return template

    async def get_pdf_bytes(self, template: OnboardingTemplate) -> bytes:
        """Read the stored PDF bytes (caller wraps in a Response)."""
        if not template.pdf_path:
            raise FileNotFoundError("Template has no PDF")
        return await storage.read_bytes(template.pdf_path)

    async def _read_pdf_bytes(self, template: OnboardingTemplate) -> bytes:
        if not template.pdf_path:
            raise FieldDefinitionError(
                "Upload a PDF before defining fields on this template."
            )
        return await storage.read_bytes(template.pdf_path)

    @staticmethod
    def _validate_field_definitions(
        template: OnboardingTemplate,
        pdf_bytes: bytes,
        field_definitions: list[dict],
    ) -> None:
        """Geometry / bounds / uniqueness / prefill checks → 422.

        Pydantic already enforced kind, slug shape, and prefill literal; this
        adds the PDF-dependent checks (page in range, box in-bounds) plus
        within-doc id uniqueness. Mirrors the
        ``service._strict_coords_for_stamper`` idiom but surfaces 422.
        """
        reader = PdfReader(io.BytesIO(pdf_bytes))
        page_count = len(reader.pages)
        seen_ids: set[str] = set()

        for index, field in enumerate(field_definitions):
            label = f"field '{field.get('id', index)}'"

            field_id = field.get("id")
            if field_id in seen_ids:
                raise FieldDefinitionError(f"Duplicate field id '{field_id}'")
            seen_ids.add(field_id)

            if field.get("prefill") not in (None, *_ALLOWED_PREFILL):
                raise FieldDefinitionError(
                    f"{label}: unsupported prefill '{field.get('prefill')}'"
                )

            page = field.get("page")
            if not isinstance(page, int) or page < 1 or page > page_count:
                raise FieldDefinitionError(
                    f"{label}: page {page} out of range (1..{page_count})"
                )

            try:
                x = float(field["x"])
                y = float(field["y"])
                w = float(field["w"])
                h = float(field["h"])
            except (KeyError, TypeError, ValueError) as exc:
                raise FieldDefinitionError(f"{label}: malformed coordinates") from exc

            if not all(math.isfinite(v) for v in (x, y, w, h)):
                raise FieldDefinitionError(f"{label}: non-finite coordinates")
            if w <= 0 or h <= 0:
                raise FieldDefinitionError(f"{label}: width and height must be positive")

            media_box = reader.pages[page - 1].mediabox
            page_w = float(media_box.width)
            page_h = float(media_box.height)
            if x < 0 or y < 0 or x + w > page_w or y + h > page_h:
                raise FieldDefinitionError(
                    f"{label}: box is outside the page bounds "
                    f"({page_w:.0f}x{page_h:.0f} pt)"
                )
