"""Audit models for tracking entity changes and active CRM work sessions."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class AuditLog(Base):
    """Audit log entry tracking changes to CRM entities."""
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    action: Mapped[str] = mapped_column(String(20), nullable=False)  # create, update, delete
    changes: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # [{field, old_value, new_value}]
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
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


class WorkSession(Base):
    """Estimated active CRM time for a user on a specific entity.

    The frontend only heartbeats while the tab is visible and the user is
    recently active. This table stores coarse active time, not keystrokes or
    screen content.
    """

    __tablename__ = "work_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
    )
    source: Mapped[str] = mapped_column(String(50), default="detail_page", nullable=False)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)

    __table_args__ = (
        Index("ix_work_sessions_user_seen", "user_id", "last_seen_at"),
        Index("ix_work_sessions_entity", "entity_type", "entity_id"),
        Index("ix_work_sessions_open", "user_id", "entity_type", "entity_id", "ended_at"),
    )
