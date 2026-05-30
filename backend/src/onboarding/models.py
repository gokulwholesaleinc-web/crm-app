"""Client Onboarding template models (Phase 1).

Holds the team-library template row: a staff-uploaded PDF plus the
field-definition overlay that the per-field stamper (Phase 2) burns into
the document. See CLIENT_ONBOARDING_PLAN.md §14 Phase 1 and the
build-order note §A.
"""

import sqlalchemy as sa
from sqlalchemy import (
    JSON,
    Boolean,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

from src.core.mixins.auditable import AuditableMixin
from src.database import Base


class _FieldDefinitions(TypeDecorator):
    """JSONB on Postgres, JSON on SQLite (test DB).

    Module-local clone of ``proposals/models.py:_SignatureCoords`` so the
    onboarding module stays self-contained (no cross-feature import).
    Stores the field-definition array (see schemas.FieldDefinition).
    """

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(JSON())


class OnboardingTemplate(Base, AuditableMixin):
    """A reusable onboarding PDF + its field-definition overlay.

    ``AuditableMixin`` supplies ``created_at``/``updated_at``/
    ``created_by_id``/``updated_by_id`` — they are NOT redeclared here.
    """

    __tablename__ = "onboarding_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    # null = universal template; controlled slug otherwise (validated in service).
    service_tag: Mapped[str | None] = mapped_column(String(100), index=True)
    owner_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )
    # Storage ref ("obj://<key>" for R2 or a path relative to uploads/ for
    # disk). Null until the first /pdf upload — field_definitions cannot be
    # saved while this is null (bounds-validation needs the page count).
    pdf_path: Mapped[str | None] = mapped_column(Text)
    pdf_version: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1", nullable=False
    )
    field_definitions: Mapped[list[dict]] = mapped_column(
        _FieldDefinitions,
        nullable=False,
        default=list,
        server_default="[]",
    )
    requires_esign: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=sa.false(), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=sa.true(), nullable=False
    )
