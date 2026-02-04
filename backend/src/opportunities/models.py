"""Opportunity/Deal model for sales pipeline."""

from datetime import date
from typing import Optional, TYPE_CHECKING
from sqlalchemy import String, Integer, ForeignKey, Text, Float, Date, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.database import Base
from src.core.mixins.auditable import AuditableMixin

if TYPE_CHECKING:
    from src.contacts.models import Contact
    from src.companies.models import Company


class PipelineStage(Base):
    """Pipeline stages for opportunities."""
    __tablename__ = "pipeline_stages"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255))
    order: Mapped[int] = mapped_column(Integer, default=0)
    color: Mapped[str] = mapped_column(String(7), default="#6366f1")
    probability: Mapped[int] = mapped_column(Integer, default=0)  # 0-100%
    is_won: Mapped[bool] = mapped_column(Boolean, default=False)
    is_lost: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Opportunity(Base, AuditableMixin):
    """Opportunity/Deal model - sales pipeline items."""
    __tablename__ = "opportunities"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Basic info
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)

    # Pipeline
    pipeline_stage_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("pipeline_stages.id"),
        nullable=False,
        index=True,
    )

    # Financials
    amount: Mapped[Optional[float]] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3), default="USD")

    # Probability override (if null, use stage probability)
    probability: Mapped[Optional[int]] = mapped_column(Integer)

    # Dates
    expected_close_date: Mapped[Optional[date]] = mapped_column(Date)
    actual_close_date: Mapped[Optional[date]] = mapped_column(Date)

    # Relationships
    contact_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("contacts.id", ondelete="SET NULL"),
        index=True,
    )
    company_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="SET NULL"),
        index=True,
    )

    # Source tracking
    source: Mapped[Optional[str]] = mapped_column(String(255))  # Lead #, Referral, etc.

    # Owner
    owner_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )

    # Loss reason (if lost)
    loss_reason: Mapped[Optional[str]] = mapped_column(String(255))
    loss_notes: Mapped[Optional[str]] = mapped_column(Text)

    # Relationships
    pipeline_stage: Mapped["PipelineStage"] = relationship(
        "PipelineStage",
        lazy="joined",
    )
    contact: Mapped[Optional["Contact"]] = relationship(
        "Contact",
        lazy="joined",
    )
    company: Mapped[Optional["Company"]] = relationship(
        "Company",
        lazy="joined",
    )

    @property
    def weighted_amount(self) -> Optional[float]:
        """Calculate weighted amount based on probability."""
        if not self.amount:
            return None
        prob = self.probability if self.probability is not None else self.pipeline_stage.probability
        return self.amount * (prob / 100)
