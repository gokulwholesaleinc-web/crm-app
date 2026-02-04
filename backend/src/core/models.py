"""Core models used across the CRM application."""

from datetime import datetime
from typing import Optional
from sqlalchemy import String, Text, Integer, ForeignKey, DateTime, func, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.database import Base
from src.core.mixins.auditable import TimestampMixin


class Note(Base, TimestampMixin):
    """
    CRMNote model - polymorphic notes that can attach to any entity.

    Based on ERPNext's CRMNote pattern.
    """
    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Polymorphic link to any entity
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False)

    # Author tracking
    created_by_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Indexes for efficient querying
    __table_args__ = (
        Index("ix_notes_entity", "entity_type", "entity_id"),
    )


class Tag(Base, TimestampMixin):
    """Tag model for flexible categorization."""
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    color: Mapped[Optional[str]] = mapped_column(String(7), default="#6366f1")  # Hex color
    description: Mapped[Optional[str]] = mapped_column(String(255))


class EntityTag(Base):
    """Junction table for polymorphic tagging."""
    __tablename__ = "entity_tags"

    id: Mapped[int] = mapped_column(primary_key=True)
    tag_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tags.id", ondelete="CASCADE"),
        nullable=False,
    )
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False)

    # Relationships
    tag: Mapped["Tag"] = relationship("Tag", lazy="joined")

    __table_args__ = (
        Index("ix_entity_tags_entity", "entity_type", "entity_id"),
        Index("ix_entity_tags_tag", "tag_id"),
    )
