"""Dashboard configuration models - ERPNext pattern."""


from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.core.mixins.auditable import TimestampMixin
from src.database import Base


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
    description: Mapped[str | None] = mapped_column(String(255))

    # Configuration (JSON string)
    # Example: {"model": "opportunities", "aggregate": "sum", "field": "amount", "filters": {"status": "open"}}
    config: Mapped[str] = mapped_column(Text, nullable=False)

    # Styling
    color: Mapped[str] = mapped_column(String(7), default="#6366f1")
    icon: Mapped[str | None] = mapped_column(String(50))

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
    description: Mapped[str | None] = mapped_column(String(255))

    # Chart type
    chart_type: Mapped[str] = mapped_column(String(20), nullable=False)  # bar, line, pie, funnel, area

    # Configuration (JSON string)
    # Example: {"model": "leads", "group_by": "status", "aggregate": "count", "date_range": "last_30_days"}
    config: Mapped[str] = mapped_column(Text, nullable=False)

    # Display settings
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    order: Mapped[int] = mapped_column(Integer, default=0)
    width: Mapped[str] = mapped_column(String(10), default="half")  # full, half, third


class DashboardReportWidget(Base, TimestampMixin):
    """
    Dashboard report widget - pins a saved report to the dashboard.

    Users can add saved reports as widgets on their dashboard with
    configurable position and width.
    """
    __tablename__ = "dashboard_report_widgets"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    report_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("saved_reports.id", ondelete="CASCADE"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(Integer, default=0)
    width: Mapped[str] = mapped_column(String(10), default="half")  # half, full
    is_visible: Mapped[bool] = mapped_column(Boolean, default=True)
