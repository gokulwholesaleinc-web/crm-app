"""Report models."""

from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func
from src.database import Base


class SavedReport(Base):
    __tablename__ = "saved_reports"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    entity_type = Column(String(50), nullable=False)
    filters = Column(Text, nullable=True)
    group_by = Column(String(100), nullable=True)
    date_group = Column(String(20), nullable=True)
    metric = Column(String(20), nullable=False, default="count")
    metric_field = Column(String(100), nullable=True)
    chart_type = Column(String(20), nullable=False, default="bar")
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    is_public = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
