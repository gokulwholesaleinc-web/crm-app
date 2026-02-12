"""Quote models for sales proposals and pricing."""

from datetime import date, datetime
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import String, Integer, ForeignKey, Text, Numeric, Date, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.database import Base
from src.core.mixins.auditable import AuditableMixin

if TYPE_CHECKING:
    from src.opportunities.models import Opportunity
    from src.contacts.models import Contact
    from src.companies.models import Company


class Quote(Base, AuditableMixin):
    """Quote model for sales proposals."""
    __tablename__ = "quotes"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Identification
    quote_number: Mapped[str] = mapped_column(
        String(50), unique=True, index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)

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

    # Status: draft, sent, viewed, accepted, rejected, expired
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)

    # Validity and currency
    valid_until: Mapped[Optional[date]] = mapped_column(Date)
    currency: Mapped[str] = mapped_column(String(3), default="USD")

    # Discount
    discount_type: Mapped[Optional[str]] = mapped_column(String(20))  # percent or fixed
    discount_value: Mapped[float] = mapped_column(Numeric(12, 2), default=0)

    # Financials (calculated from line items)
    subtotal: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    tax_rate: Mapped[float] = mapped_column(Numeric(5, 4), default=0)
    tax_amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    total: Mapped[float] = mapped_column(Numeric(12, 2), default=0)

    # Terms
    terms_and_conditions: Mapped[Optional[str]] = mapped_column(Text)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # Owner
    owner_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )

    # Timestamps for status transitions
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    rejected_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # ORM relationships
    line_items: Mapped[List["QuoteLineItem"]] = relationship(
        "QuoteLineItem",
        back_populates="quote",
        cascade="all, delete-orphan",
        order_by="QuoteLineItem.sort_order",
        lazy="selectin",
    )
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


class QuoteLineItem(Base):
    """Line items within a quote."""
    __tablename__ = "quote_line_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    quote_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("quotes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(10, 2), default=1)
    unit_price: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    discount: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    total: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    # ORM relationship
    quote: Mapped["Quote"] = relationship("Quote", back_populates="line_items")


class QuoteTemplate(Base, AuditableMixin):
    """Reusable quote templates."""
    __tablename__ = "quote_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    default_terms: Mapped[Optional[str]] = mapped_column(Text)
    default_notes: Mapped[Optional[str]] = mapped_column(Text)
    line_items_template: Mapped[Optional[dict]] = mapped_column(JSON)
