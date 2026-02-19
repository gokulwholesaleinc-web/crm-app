"""Lead model for CRM lead management."""

from typing import Optional
from sqlalchemy import String, Integer, ForeignKey, Text, Float, Enum as SQLEnum, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.database import Base
from src.core.mixins.auditable import AuditableMixin
import enum


class LeadStatus(str, enum.Enum):
    NEW = "new"
    CONTACTED = "contacted"
    QUALIFIED = "qualified"
    UNQUALIFIED = "unqualified"
    CONVERTED = "converted"
    LOST = "lost"


class LeadSource(Base):
    """Lead source tracking."""
    __tablename__ = "lead_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(default=True)


class Lead(Base, AuditableMixin):
    """Lead model - potential customers/opportunities."""
    __tablename__ = "leads"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Basic info
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(255), index=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50))
    mobile: Mapped[Optional[str]] = mapped_column(String(50))

    # Professional info
    job_title: Mapped[Optional[str]] = mapped_column(String(100))
    company_name: Mapped[Optional[str]] = mapped_column(String(255))
    website: Mapped[Optional[str]] = mapped_column(String(500))
    industry: Mapped[Optional[str]] = mapped_column(String(100))

    # Source tracking
    source_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("lead_sources.id", ondelete="SET NULL"),
        index=True,
    )
    source_details: Mapped[Optional[str]] = mapped_column(String(500))

    # Lead scoring
    score: Mapped[int] = mapped_column(Integer, default=0)
    score_factors: Mapped[Optional[str]] = mapped_column(Text)  # JSON string of scoring factors

    # Status
    status: Mapped[str] = mapped_column(
        String(20),
        default=LeadStatus.NEW.value,
        index=True,
    )

    # Address
    address_line1: Mapped[Optional[str]] = mapped_column(String(255))
    address_line2: Mapped[Optional[str]] = mapped_column(String(255))
    city: Mapped[Optional[str]] = mapped_column(String(100))
    state: Mapped[Optional[str]] = mapped_column(String(100))
    postal_code: Mapped[Optional[str]] = mapped_column(String(20))
    country: Mapped[Optional[str]] = mapped_column(String(100))

    # Additional info
    description: Mapped[Optional[str]] = mapped_column(Text)
    requirements: Mapped[Optional[str]] = mapped_column(Text)

    # Budget and timeline
    budget_amount: Mapped[Optional[float]] = mapped_column(Float)
    budget_currency: Mapped[str] = mapped_column(String(3), default="USD")

    # Owner
    owner_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )

    # Conversion tracking (ERPNext pattern)
    converted_contact_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("contacts.id", ondelete="SET NULL"),
    )
    converted_opportunity_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("opportunities.id", ondelete="SET NULL"),
    )

    # Relationships
    source: Mapped[Optional["LeadSource"]] = relationship("LeadSource", lazy="joined")

    __table_args__ = (
        Index("ix_leads_owner_created", "owner_id", "created_at"),
    )

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"
