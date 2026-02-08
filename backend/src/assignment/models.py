"""Lead auto-assignment models."""

from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, ForeignKey, Boolean, DateTime, func, JSON
from sqlalchemy.orm import Mapped, mapped_column
from src.database import Base


class AssignmentRule(Base):
    """Rule for automatically assigning leads to team members."""
    __tablename__ = "assignment_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Assignment type: round_robin or load_balance
    assignment_type: Mapped[str] = mapped_column(String(20), nullable=False)

    # List of user IDs to assign to
    user_ids: Mapped[list] = mapped_column(JSON, nullable=False)

    # Optional filters as JSON: {"source": "Website", "tags": [1, 2]}
    filters: Mapped[Optional[dict]] = mapped_column(JSON)

    # For round-robin: index of the last assigned user
    last_assigned_index: Mapped[int] = mapped_column(Integer, default=-1)

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
