"""Proposal models for AI-assisted sales proposals."""

from datetime import date, datetime
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import String, Integer, ForeignKey, Text, Date, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.database import Base
from src.core.mixins.auditable import AuditableMixin

if TYPE_CHECKING:
    from src.opportunities.models import Opportunity
    from src.contacts.models import Contact
    from src.companies.models import Company
    from src.quotes.models import Quote


class Proposal(Base, AuditableMixin):
    """Proposal model for AI-generated sales proposals."""
    __tablename__ = "proposals"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Identification
    proposal_number: Mapped[str] = mapped_column(
        String(50), unique=True, index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[Optional[str]] = mapped_column(Text)

    # Relationships to other entities
    opportunity_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("opportunities.id", ondelete="SET NULL"),
        index=True,
    )
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
    quote_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("quotes.id", ondelete="SET NULL"),
        index=True,
    )

    # Status: draft, sent, viewed, accepted, rejected
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)

    # Content sections
    cover_letter: Mapped[Optional[str]] = mapped_column(Text)
    executive_summary: Mapped[Optional[str]] = mapped_column(Text)
    scope_of_work: Mapped[Optional[str]] = mapped_column(Text)
    pricing_section: Mapped[Optional[str]] = mapped_column(Text)
    timeline: Mapped[Optional[str]] = mapped_column(Text)
    terms: Mapped[Optional[str]] = mapped_column(Text)

    # Validity
    valid_until: Mapped[Optional[date]] = mapped_column(Date)

    # Status timestamps
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    viewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    rejected_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # View tracking
    view_count: Mapped[int] = mapped_column(Integer, default=0)
    last_viewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Owner
    owner_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )

    # ORM relationships
    opportunity: Mapped[Optional["Opportunity"]] = relationship(
        "Opportunity",
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
    quote: Mapped[Optional["Quote"]] = relationship(
        "Quote",
        lazy="joined",
    )
    views: Mapped[List["ProposalView"]] = relationship(
        "ProposalView",
        back_populates="proposal",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class ProposalTemplate(Base, AuditableMixin):
    """Reusable proposal templates with variable placeholders."""
    __tablename__ = "proposal_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    category: Mapped[Optional[str]] = mapped_column(String(100))
    content_template: Mapped[Optional[str]] = mapped_column(Text)


class ProposalView(Base):
    """Tracks individual views of a proposal."""
    __tablename__ = "proposal_views"

    id: Mapped[int] = mapped_column(primary_key=True)
    proposal_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("proposals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    viewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))
    user_agent: Mapped[Optional[str]] = mapped_column(Text)

    # ORM relationship
    proposal: Mapped["Proposal"] = relationship("Proposal", back_populates="views")
