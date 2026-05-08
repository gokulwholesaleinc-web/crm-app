"""Lead auto-assignment models."""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, func
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
    filters: Mapped[dict | None] = mapped_column(JSON)

    # For round-robin: index of the last assigned user
    last_assigned_index: Mapped[int] = mapped_column(Integer, default=-1)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Catch-all rule that fires when no filtered rule matches. Partial
    # unique index in the DB enforces "at most one default".
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    created_by_id: Mapped[int | None] = mapped_column(
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


class AssignmentLog(Base):
    """Audit trail for every auto-assignment decision.

    `reason` records *why* this user got the lead — `rule_match` (a
    filtered rule fired), `default_fallback` (the catch-all rule fired
    because no filter matched), or `manual_override` (an admin
    reassign action so the count isn't double-charged to the rule's
    load-balance math). Read by the per-rule stats panel and any
    future reporting widget.
    """
    __tablename__ = "assignment_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    lead_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("leads.id", ondelete="CASCADE"), nullable=False
    )
    rule_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("assignment_rules.id", ondelete="SET NULL")
    )
    assigned_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL")
    )
    reason: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
