"""Dashboard configuration models - ERPNext pattern."""

from typing import Optional
from sqlalchemy import String, Integer, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from src.database import Base
from src.core.mixins.auditable import TimestampMixin


class DashboardNumberCard(Base, TimestampMixin):
    """
    Number card configuration - ERPNext pattern.

    Stores configuration for KPI number cards displayed on dashboard.
    """
    __tablename__ = "dashboard_number_cards"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Display
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255))

    # Configuration (JSON string)
    # Example: {"model": "opportunities", "aggregate": "sum", "field": "amount", "filters": {"status": "open"}}
    config: Mapped[str] = mapped_column(Text, nullable=False)

    # Styling
    color: Mapped[str] = mapped_column(String(7), default="#6366f1")
    icon: Mapped[Optional[str]] = mapped_column(String(50))

    # Display settings
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    order: Mapped[int] = mapped_column(Integer, default=0)
    show_percentage_change: Mapped[bool] = mapped_column(Boolean, default=False)


class DashboardChart(Base, TimestampMixin):
    """
    Dashboard chart configuration - ERPNext pattern.

    Stores configuration for charts displayed on dashboard.
    """
    __tablename__ = "dashboard_charts"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Display
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255))

    # Chart type
    chart_type: Mapped[str] = mapped_column(String(20), nullable=False)  # bar, line, pie, funnel, area

    # Configuration (JSON string)
    # Example: {"model": "leads", "group_by": "status", "aggregate": "count", "date_range": "last_30_days"}
    config: Mapped[str] = mapped_column(Text, nullable=False)

    # Display settings
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    order: Mapped[int] = mapped_column(Integer, default=0)
    width: Mapped[str] = mapped_column(String(10), default="half")  # full, half, third
