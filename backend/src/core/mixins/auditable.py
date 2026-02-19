"""Auditable mixin for tracking creation and modification metadata."""

from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, ForeignKey, func
from sqlalchemy.orm import declared_attr, Mapped, mapped_column


class TimestampMixin:
    """Mixin that adds created_at and updated_at timestamps."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class AuditableMixin(TimestampMixin):
    """Mixin that adds audit fields for tracking who created/modified records."""

    @declared_attr
    def created_by_id(cls) -> Mapped[int | None]:
        return mapped_column(
            Integer,
            ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        )

    @declared_attr
    def updated_by_id(cls) -> Mapped[int | None]:
        return mapped_column(
            Integer,
            ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        )
