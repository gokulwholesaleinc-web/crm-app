"""Attachment model for file uploads linked to CRM entities."""

from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, ForeignKey, BigInteger, DateTime, Index, func
from sqlalchemy.orm import Mapped, mapped_column
from src.database import Base


class Attachment(Base):
    """File attachment linked to any CRM entity via polymorphic relationship."""
    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(primary_key=True)

    # File metadata
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)

    # Polymorphic link to any entity
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False)

    # Author tracking
    uploaded_by: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_attachments_entity", "entity_type", "entity_id"),
    )
