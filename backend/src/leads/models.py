"""Lead model for CRM lead management."""

import enum
from typing import Optional

from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.mixins.auditable import AuditableMixin
from src.database import Base


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
    description: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(default=True)


class Lead(Base, AuditableMixin):
    """Lead model - potential customers/opportunities."""
    __tablename__ = "leads"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Basic info
    first_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), index=True)
    phone: Mapped[str | None] = mapped_column(String(50))
    mobile: Mapped[str | None] = mapped_column(String(50))

    # Professional info
    job_title: Mapped[str | None] = mapped_column(String(100))
    company_name: Mapped[str | None] = mapped_column(String(255))
    website: Mapped[str | None] = mapped_column(String(500))
    industry: Mapped[str | None] = mapped_column(String(100))

    # Source tracking
    source_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("lead_sources.id", ondelete="SET NULL"),
        index=True,
    )
    source_details: Mapped[str | None] = mapped_column(String(500))

    # Lead scoring
    score: Mapped[int] = mapped_column(Integer, default=0)
    score_factors: Mapped[str | None] = mapped_column(Text)  # JSON string of scoring factors

    # Status
    status: Mapped[str] = mapped_column(
        String(20),
        default=LeadStatus.NEW.value,
        index=True,
    )

    # Address
    address_line1: Mapped[str | None] = mapped_column(String(255))
    address_line2: Mapped[str | None] = mapped_column(String(255))
    city: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(100))
    postal_code: Mapped[str | None] = mapped_column(String(20))
    country: Mapped[str | None] = mapped_column(String(100))

    # Additional info
    description: Mapped[str | None] = mapped_column(Text)
    requirements: Mapped[str | None] = mapped_column(Text)

    # Budget and timeline
    budget_amount: Mapped[float | None] = mapped_column(Float)
    budget_currency: Mapped[str] = mapped_column(String(3), default="USD")

    # Pipeline stage (for kanban board)
    pipeline_stage_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("pipeline_stages.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Owner
    owner_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )

    # Sales code
    sales_code: Mapped[str | None] = mapped_column(String(100), index=True, nullable=True)

    # Conversion tracking (ERPNext pattern)
    converted_contact_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("contacts.id", ondelete="SET NULL"),
    )
    converted_opportunity_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("opportunities.id", ondelete="SET NULL"),
    )

    # Dedup merge forwarding pointer — see Contact.merged_into_id.
    merged_into_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("leads.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    source: Mapped[Optional["LeadSource"]] = relationship("LeadSource", lazy="joined")
    pipeline_stage = relationship("PipelineStage", lazy="joined")

    __table_args__ = (
        Index("ix_leads_owner_created", "owner_id", "created_at"),
    )

    @property
    def full_name(self) -> str:
        name = " ".join(p for p in (self.first_name, self.last_name) if p)
        return name or self.company_name or ""
