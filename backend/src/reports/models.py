"""SavedReport model for persisting custom report definitions."""

from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, ForeignKey, Text, Boolean, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from src.database import Base


class SavedReport(Base):
    """Saved report definition that users can create and reuse."""
    __tablename__ = "saved_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    filters: Mapped[Optional[str]] = mapped_column(Text)  # JSON filter definition
    group_by: Mapped[Optional[str]] = mapped_column(String(100))
    date_group: Mapped[Optional[str]] = mapped_column(String(20))  # day, week, month, quarter, year
    metric: Mapped[str] = mapped_column(String(20), default="count")  # count, sum, avg, min, max
    metric_field: Mapped[Optional[str]] = mapped_column(String(100))  # field to apply metric on
    chart_type: Mapped[str] = mapped_column(String(20), default="bar")  # bar, line, pie, table, funnel
    created_by_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)

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
