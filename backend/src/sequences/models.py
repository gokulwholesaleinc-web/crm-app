"""Sales sequence models."""

from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, ForeignKey, Text, Boolean, DateTime, func, JSON
from sqlalchemy.orm import Mapped, mapped_column
from src.database import Base


class Sequence(Base):
    """Sales sequence with ordered steps for contact engagement."""
    __tablename__ = "sequences"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)

    # Steps as JSON list: [{step_number, type: email|task|wait, delay_days, template_id, task_description}]
    steps: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_by_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class SequenceEnrollment(Base):
    """Enrollment of a contact in a sequence."""
    __tablename__ = "sequence_enrollments"

    id: Mapped[int] = mapped_column(primary_key=True)

    sequence_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sequences.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    contact_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("contacts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    current_step: Mapped[int] = mapped_column(Integer, default=0)

    # Status: active, paused, completed, cancelled
    status: Mapped[str] = mapped_column(String(20), default="active")

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    next_step_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
