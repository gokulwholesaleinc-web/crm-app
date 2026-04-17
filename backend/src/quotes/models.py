"""Quote models for sales proposals and pricing."""

from datetime import date, datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.mixins.auditable import AuditableMixin
from src.database import Base

if TYPE_CHECKING:
    from src.companies.models import Company
    from src.contacts.models import Contact
    from src.opportunities.models import Opportunity


class Quote(Base, AuditableMixin):
    """Quote model for sales proposals."""
    __tablename__ = "quotes"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Identification
    quote_number: Mapped[str] = mapped_column(
        String(50), unique=True, index=True, nullable=False
    )
    # Unguessable token used for the public /accept endpoint. Separate from
    # quote_number so the user-facing identifier can stay short and readable
    # while the public URL remains non-enumerable.
    public_token: Mapped[str | None] = mapped_column(
        String(64), unique=True, index=True, nullable=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    # Relationships to other entities
    opportunity_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("opportunities.id", ondelete="SET NULL"),
        index=True,
    )
    contact_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("contacts.id", ondelete="SET NULL"),
        index=True,
    )
    company_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="SET NULL"),
        index=True,
    )

    # Status: draft, sent, viewed, accepted, rejected, expired
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)

    # Payment type: one_time or subscription
    payment_type: Mapped[str] = mapped_column(
        String(20), default="one_time", nullable=False
    )
    recurring_interval: Mapped[str | None] = mapped_column(
        String(20)
    )  # monthly, quarterly, yearly

    # Validity and currency
    valid_until: Mapped[date | None] = mapped_column(Date)
    currency: Mapped[str] = mapped_column(String(3), default="USD")

    # Discount
    discount_type: Mapped[str | None] = mapped_column(String(20))  # percent or fixed
    discount_value: Mapped[float] = mapped_column(Numeric(12, 2), default=0)

    # Financials (calculated from line items)
    subtotal: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    tax_rate: Mapped[float] = mapped_column(Numeric(5, 4), default=0)
    tax_amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    total: Mapped[float] = mapped_column(Numeric(12, 2), default=0)

    # Terms
    terms_and_conditions: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)

    # Owner
    owner_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )

    # Timestamps for status transitions
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # E-signature fields (captured when client accepts via public link)
    signer_name: Mapped[str | None] = mapped_column(String(255))
    signer_email: Mapped[str | None] = mapped_column(String(255))
    signer_ip: Mapped[str | None] = mapped_column(String(45))
    signer_user_agent: Mapped[str | None] = mapped_column(Text)
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    # Optional override for who may sign. NULL falls back to contact.email.
    designated_signer_email: Mapped[str | None] = mapped_column(String(255))

    # ORM relationships
    line_items: Mapped[list["QuoteLineItem"]] = relationship(
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
    description: Mapped[str | None] = mapped_column(Text)
    default_terms: Mapped[str | None] = mapped_column(Text)
    default_notes: Mapped[str | None] = mapped_column(Text)
    line_items_template: Mapped[dict | None] = mapped_column(JSON)


class ProductBundle(Base, AuditableMixin):
    """Reusable product bundle grouping multiple items."""
    __tablename__ = "product_bundles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    # ORM relationships
    items: Mapped[list["ProductBundleItem"]] = relationship(
        "ProductBundleItem",
        back_populates="bundle",
        cascade="all, delete-orphan",
        order_by="ProductBundleItem.sort_order",
        lazy="selectin",
    )


class ProductBundleItem(Base):
    """Individual item within a product bundle."""
    __tablename__ = "product_bundle_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    bundle_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("product_bundles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(10, 2), default=1)
    unit_price: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    # ORM relationship
    bundle: Mapped["ProductBundle"] = relationship("ProductBundle", back_populates="items")
