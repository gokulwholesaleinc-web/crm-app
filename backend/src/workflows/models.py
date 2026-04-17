"""Workflow automation models."""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class WorkflowRule(Base):
    """Workflow automation rule that triggers actions based on entity events."""
    __tablename__ = "workflow_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Trigger configuration
    trigger_entity: Mapped[str] = mapped_column(String(50), nullable=False)  # lead, opportunity, contact, activity
    trigger_event: Mapped[str] = mapped_column(String(50), nullable=False)  # created, updated, status_changed, score_changed

    # Conditions as JSON - e.g., {"field": "score", "operator": ">=", "value": 80}
    conditions: Mapped[dict | None] = mapped_column(JSON)

    # Actions as JSON list - e.g., [{"type": "assign_owner", "value": 1}]
    actions: Mapped[list | None] = mapped_column(JSON)

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


class WorkflowExecution(Base):
    """Record of a workflow rule execution."""
    __tablename__ = "workflow_executions"

    id: Mapped[int] = mapped_column(primary_key=True)

    rule_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("workflow_rules.id", ondelete="CASCADE"),
        nullable=False,
    )

    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False)

    status: Mapped[str] = mapped_column(String(20), nullable=False)  # success, failed, skipped
    result: Mapped[dict | None] = mapped_column(JSON)

    executed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
