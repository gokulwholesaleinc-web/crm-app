"""Attachment model."""

from typing import Optional
from sqlalchemy import String, Integer, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column
from src.database import Base
from src.core.mixins.auditable import AuditableMixin


class Attachment(Base, AuditableMixin):
    """File attachment for any entity."""
    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    content_type: Mapped[Optional[str]] = mapped_column(String(100))
    file_size: Mapped[Optional[int]] = mapped_column(Integer)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False)
