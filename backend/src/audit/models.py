"""Audit log model for tracking entity changes."""

from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, ForeignKey, Text, DateTime, func, Index, JSON
from sqlalchemy.orm import Mapped, mapped_column
from src.database import Base


class AuditLog(Base):
    """Audit log entry tracking changes to CRM entities."""
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    action: Mapped[str] = mapped_column(String(20), nullable=False)  # create, update, delete
    changes: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # [{field, old_value, new_value}]
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_audit_logs_entity", "entity_type", "entity_id"),
        Index("ix_audit_logs_user", "user_id"),
        Index("ix_audit_logs_timestamp", "timestamp"),
    )
